from datetime import datetime

from django.contrib.auth import authenticate
from django.db import transaction
from django.db.models import F, Sum
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Bundle, BundlePerformance, Discount, Performance, Show, TicketOrder
from .serializers import (
    BundleOrderCreateSerializer,
    BundleSerializer,
    BundleStatsSerializer,
    DiscountSerializer,
    DiscountStatsSerializer,
    LoginSerializer,
    OrderCreateSerializer,
    OrderSerializer,
    PerformanceSerializer,
    PriceCalculateResultSerializer,
    PriceCalculateSerializer,
    ShowSerializer,
)


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        s = LoginSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        user = authenticate(username=s.validated_data["username"], password=s.validated_data["password"])
        if user is None:
            return Response({"detail": "用户名或密码错误"}, status=status.HTTP_401_UNAUTHORIZED)
        token = RefreshToken.for_user(user)
        return Response({"access_token": str(token.access_token), "token_type": "bearer"})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request):
    u = request.user
    return Response({"id": u.id, "username": u.username, "display_name": u.get_full_name() or "平台管理员"})


class ShowViewSet(viewsets.ModelViewSet):
    queryset = Show.objects.all().order_by("id")
    serializer_class = ShowSerializer


class PerformanceViewSet(viewsets.ModelViewSet):
    queryset = Performance.objects.select_related("show").all().order_by("start_at")
    serializer_class = PerformanceSerializer


def calculate_discount_amount(discount, original_amount):
    """计算优惠金额，返回(优惠金额, 最终金额, 是否适用, 原因)。"""
    if not discount.is_active:
        return 0, original_amount, False, "优惠已停用"

    now = datetime.now()
    if now < discount.valid_from or now > discount.valid_to:
        return 0, original_amount, False, "优惠不在有效期内"

    if original_amount < discount.min_amount:
        return 0, original_amount, False, f"未达到最低消费门槛 {discount.min_amount} 元"

    if discount.discount_type == "fixed":
        discount_value = float(discount.value)
        if discount_value <= 0 or discount_value > 1:
            return 0, original_amount, False, "折扣值无效"
        discount_amount = original_amount * (1 - discount_value)
    elif discount.discount_type == "full_reduction":
        discount_amount = float(discount.value)
    else:
        return 0, original_amount, False, "未知优惠类型"

    discount_amount = round(discount_amount, 2)
    final_amount = max(0, round(original_amount - discount_amount, 2))
    return discount_amount, final_amount, True, ""


def is_discount_applicable_to_item(discount, performance=None, bundle=None):
    """检查优惠是否适用于指定的场次或套票。"""
    has_perf_restriction = discount.applicable_performances.exists()
    has_bundle_restriction = discount.applicable_bundles.exists()

    if not has_perf_restriction and not has_bundle_restriction:
        return True

    if performance and has_perf_restriction:
        return discount.applicable_performances.filter(id=performance.id).exists()

    if bundle and has_bundle_restriction:
        return discount.applicable_bundles.filter(id=bundle.id).exists()

    return False


def get_applicable_discounts(original_amount, performance=None, bundle=None):
    """获取所有可用的优惠及其计算结果，返回最便宜的。"""
    now = datetime.now()
    all_discounts = Discount.objects.filter(
        is_active=True,
        valid_from__lte=now,
        valid_to__gte=now,
        min_amount__lte=original_amount,
    ).prefetch_related("applicable_performances", "applicable_bundles")

    results = []
    for discount in all_discounts:
        if not is_discount_applicable_to_item(discount, performance, bundle):
            continue
        discount_amount, final_amount, applicable, reason = calculate_discount_amount(discount, original_amount)
        results.append({
            "discount": discount,
            "applicable": applicable,
            "original_amount": original_amount,
            "discount_amount": discount_amount,
            "final_amount": final_amount,
            "reason": reason,
        })

    results.sort(key=lambda x: x["final_amount"])
    return results


class BundleViewSet(viewsets.ModelViewSet):
    queryset = Bundle.objects.prefetch_related("performances", "performances__show").all().order_by("id")
    serializer_class = BundleSerializer

    @action(detail=False, methods=["get"], url_path="stats")
    def stats(self, request):
        bundles = Bundle.objects.all()
        stats = []
        for bundle in bundles:
            sold = TicketOrder.objects.filter(bundle=bundle, status="paid").aggregate(
                total=Sum("quantity"),
                revenue=Sum("amount"),
            )
            stats.append({
                "bundle_id": bundle.id,
                "bundle_name": bundle.name,
                "total_sold": sold["total"] or 0,
                "total_revenue": sold["revenue"] or 0,
            })
        return Response(BundleStatsSerializer(stats, many=True).data)


class DiscountViewSet(viewsets.ModelViewSet):
    queryset = Discount.objects.prefetch_related(
        "applicable_performances", "applicable_performances__show",
        "applicable_bundles"
    ).all().order_by("id")
    serializer_class = DiscountSerializer

    @action(detail=False, methods=["get"], url_path="stats")
    def stats(self, request):
        discounts = Discount.objects.all()
        stats = []
        for discount in discounts:
            usage = TicketOrder.objects.filter(discount=discount, status="paid").aggregate(
                count=Sum("quantity"),
                total_discount=Sum("discount_amount"),
            )
            stats.append({
                "discount_id": discount.id,
                "discount_name": discount.name,
                "usage_count": usage["count"] or 0,
                "total_discount_amount": usage["total_discount"] or 0,
            })
        return Response(DiscountStatsSerializer(stats, many=True).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def price_calculate(request):
    s = PriceCalculateSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    data = s.validated_data

    performance = None
    bundle = None
    original_amount = 0

    if data.get("performance"):
        try:
            performance = Performance.objects.select_related("show").get(pk=data["performance"])
            original_amount = float(performance.price) * data["quantity"]
        except Performance.DoesNotExist:
            return Response({"detail": "场次不存在"}, status=status.HTTP_404_NOT_FOUND)

    if data.get("bundle"):
        try:
            bundle = Bundle.objects.prefetch_related("performances").get(pk=data["bundle"])
            if not bundle.is_active:
                return Response({"detail": "套票已停用"}, status=status.HTTP_400_BAD_REQUEST)
            if bundle.available_stock < data["quantity"]:
                return Response({"detail": "套票库存不足"}, status=status.HTTP_409_CONFLICT)
            original_amount = float(bundle.price) * data["quantity"]
        except Bundle.DoesNotExist:
            return Response({"detail": "套票不存在"}, status=status.HTTP_404_NOT_FOUND)

    original_amount = round(original_amount, 2)

    all_results = get_applicable_discounts(original_amount, performance, bundle)

    specified_discount = None
    if data.get("discount_id"):
        try:
            specified_discount = Discount.objects.get(pk=data["discount_id"])
            if not is_discount_applicable_to_item(specified_discount, performance, bundle):
                specified_discount = None
        except Discount.DoesNotExist:
            pass

    if specified_discount:
        discount_amount, final_amount, applicable, reason = calculate_discount_amount(specified_discount, original_amount)
        best_discount = {
            "discount": specified_discount,
            "applicable": applicable,
            "original_amount": original_amount,
            "discount_amount": discount_amount,
            "final_amount": final_amount,
            "reason": reason,
        }
    elif all_results and all_results[0]["applicable"]:
        best_discount = all_results[0]
    else:
        best_discount = None

    final_amount = best_discount["final_amount"] if best_discount and best_discount["applicable"] else original_amount

    result = {
        "original_amount": original_amount,
        "best_discount": best_discount,
        "all_applicable_discounts": all_results,
        "final_amount": final_amount,
    }

    return Response(PriceCalculateResultSerializer(result).data)


class OrderViewSet(viewsets.ModelViewSet):
    queryset = TicketOrder.objects.select_related(
        "performance", "performance__show", "bundle", "discount"
    ).all().order_by("-id")
    http_method_names = ["get", "post"]

    def get_serializer_class(self):
        if self.action == "create":
            return OrderCreateSerializer
        if self.action == "create_bundle":
            return BundleOrderCreateSerializer
        return OrderSerializer

    def create(self, request, *args, **kwargs):
        s = OrderCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data

        try:
            perf = Performance.objects.select_related("show").get(pk=data["performance"])
        except Performance.DoesNotExist:
            return Response({"detail": "场次不存在"}, status=status.HTTP_404_NOT_FOUND)

        remaining = perf.remaining_seats
        if data["quantity"] > remaining:
            return Response({"detail": "余票不足"}, status=status.HTTP_409_CONFLICT)

        original_amount = float(perf.price) * data["quantity"]
        discount_amount = 0
        discount_obj = None

        if data.get("discount_id"):
            try:
                discount_obj = Discount.objects.get(pk=data["discount_id"])
                if not is_discount_applicable_to_item(discount_obj, performance=perf):
                    return Response({"detail": "该优惠不适用此场次"}, status=status.HTTP_400_BAD_REQUEST)
                disc_amount, final_amount, applicable, reason = calculate_discount_amount(discount_obj, original_amount)
                if not applicable:
                    return Response({"detail": reason}, status=status.HTTP_400_BAD_REQUEST)
                discount_amount = disc_amount
            except Discount.DoesNotExist:
                return Response({"detail": "优惠不存在"}, status=status.HTTP_404_NOT_FOUND)

        final_amount = round(original_amount - discount_amount, 2)

        with transaction.atomic():
            order = TicketOrder.objects.create(
                performance=perf,
                bundle=None,
                discount=discount_obj,
                customer_name=data["customer_name"],
                phone=data.get("phone", ""),
                quantity=data["quantity"],
                original_amount=round(original_amount, 2),
                discount_amount=round(discount_amount, 2),
                amount=final_amount,
                status="paid",
            )
            perf.sold_seats = F("sold_seats") + data["quantity"]
            perf.save(update_fields=["sold_seats"])

        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"], url_path="bundle")
    def create_bundle(self, request):
        s = BundleOrderCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data

        try:
            bundle = Bundle.objects.prefetch_related("performances").get(pk=data["bundle"])
        except Bundle.DoesNotExist:
            return Response({"detail": "套票不存在"}, status=status.HTTP_404_NOT_FOUND)

        if not bundle.is_active:
            return Response({"detail": "套票已停用"}, status=status.HTTP_400_BAD_REQUEST)

        if bundle.available_stock < data["quantity"]:
            return Response({"detail": "套票库存不足"}, status=status.HTTP_409_CONFLICT)

        original_amount = float(bundle.price) * data["quantity"]
        discount_amount = 0
        discount_obj = None

        if data.get("discount_id"):
            try:
                discount_obj = Discount.objects.get(pk=data["discount_id"])
                if not is_discount_applicable_to_item(discount_obj, bundle=bundle):
                    return Response({"detail": "该优惠不适用此套票"}, status=status.HTTP_400_BAD_REQUEST)
                disc_amount, final_amount, applicable, reason = calculate_discount_amount(discount_obj, original_amount)
                if not applicable:
                    return Response({"detail": reason}, status=status.HTTP_400_BAD_REQUEST)
                discount_amount = disc_amount
            except Discount.DoesNotExist:
                return Response({"detail": "优惠不存在"}, status=status.HTTP_404_NOT_FOUND)

        final_amount = round(original_amount - discount_amount, 2)

        with transaction.atomic():
            order = TicketOrder.objects.create(
                performance=None,
                bundle=bundle,
                discount=discount_obj,
                customer_name=data["customer_name"],
                phone=data.get("phone", ""),
                quantity=data["quantity"],
                original_amount=round(original_amount, 2),
                discount_amount=round(discount_amount, 2),
                amount=final_amount,
                status="paid",
            )

            for perf in bundle.performances.all():
                if perf.remaining_seats < data["quantity"]:
                    return Response({"detail": f"场次 {perf.show.title}({perf.hall}) 余票不足"}, status=status.HTTP_409_CONFLICT)
                perf.sold_seats = F("sold_seats") + data["quantity"]
                perf.save(update_fields=["sold_seats"])

        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard_stats(request):
    show_total = Show.objects.count()
    show_on_sale = Show.objects.filter(status="on_sale").count()
    perf_total = Performance.objects.count()
    order_paid = TicketOrder.objects.filter(status="paid").count()
    sold = sum(p.sold_seats for p in Performance.objects.all())
    capacity = sum(p.total_seats for p in Performance.objects.all())
    return Response({
        "show_total": show_total,
        "show_on_sale": show_on_sale,
        "performance_total": perf_total,
        "order_paid": order_paid,
        "seats_sold": sold,
        "seats_capacity": capacity,
    })
