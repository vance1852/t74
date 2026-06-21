from rest_framework import serializers

from .models import Bundle, Discount, Performance, Show, TicketOrder


class ShowSerializer(serializers.ModelSerializer):
    class Meta:
        model = Show
        fields = ["id", "title", "troupe", "genre", "status", "created_at"]
        read_only_fields = ["id", "created_at"]


class PerformanceSerializer(serializers.ModelSerializer):
    show_title = serializers.CharField(source="show.title", read_only=True)
    remaining_seats = serializers.SerializerMethodField()

    class Meta:
        model = Performance
        fields = [
            "id", "show", "show_title", "hall", "start_at",
            "total_seats", "sold_seats", "remaining_seats", "price", "created_at",
        ]
        read_only_fields = ["id", "sold_seats", "created_at"]

    def get_remaining_seats(self, obj):
        return obj.remaining_seats


class PerformanceSimpleSerializer(serializers.ModelSerializer):
    show_title = serializers.CharField(source="show.title", read_only=True)

    class Meta:
        model = Performance
        fields = ["id", "show", "show_title", "hall", "start_at", "price"]


class BundleSimpleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bundle
        fields = ["id", "name", "description", "price", "is_active"]


class BundleSerializer(serializers.ModelSerializer):
    performances = PerformanceSimpleSerializer(many=True, read_only=True)
    performance_ids = serializers.ListField(
        child=serializers.IntegerField(), write_only=True, required=False
    )
    available_stock = serializers.IntegerField(read_only=True)
    is_sold_out = serializers.BooleanField(read_only=True)

    class Meta:
        model = Bundle
        fields = [
            "id", "name", "description", "price", "is_active",
            "performances", "performance_ids", "available_stock", "is_sold_out", "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def create(self, validated_data):
        performance_ids = validated_data.pop("performance_ids", [])
        bundle = Bundle.objects.create(**validated_data)
        if performance_ids:
            bundle.performances.set(performance_ids)
        return bundle

    def update(self, instance, validated_data):
        performance_ids = validated_data.pop("performance_ids", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if performance_ids is not None:
            instance.performances.set(performance_ids)
        return instance


class DiscountSerializer(serializers.ModelSerializer):
    applicable_performance_ids = serializers.ListField(
        child=serializers.IntegerField(), write_only=True, required=False
    )
    applicable_bundle_ids = serializers.ListField(
        child=serializers.IntegerField(), write_only=True, required=False
    )
    applicable_performances = PerformanceSimpleSerializer(many=True, read_only=True)
    applicable_bundles = BundleSimpleSerializer(many=True, read_only=True)

    class Meta:
        model = Discount
        fields = [
            "id", "name", "discount_type", "value", "min_amount",
            "valid_from", "valid_to", "is_active",
            "applicable_performances", "applicable_bundles",
            "applicable_performance_ids", "applicable_bundle_ids",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def create(self, validated_data):
        perf_ids = validated_data.pop("applicable_performance_ids", [])
        bundle_ids = validated_data.pop("applicable_bundle_ids", [])
        discount = Discount.objects.create(**validated_data)
        if perf_ids:
            discount.applicable_performances.set(perf_ids)
        if bundle_ids:
            discount.applicable_bundles.set(bundle_ids)
        return discount

    def update(self, instance, validated_data):
        perf_ids = validated_data.pop("applicable_performance_ids", None)
        bundle_ids = validated_data.pop("applicable_bundle_ids", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if perf_ids is not None:
            instance.applicable_performances.set(perf_ids)
        if bundle_ids is not None:
            instance.applicable_bundles.set(bundle_ids)
        return instance


class DiscountSimpleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Discount
        fields = ["id", "name", "discount_type", "value", "min_amount", "valid_from", "valid_to"]


class DiscountDetailSerializer(serializers.Serializer):
    discount = DiscountSimpleSerializer()
    applicable = serializers.BooleanField()
    original_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    discount_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    final_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    reason = serializers.CharField(required=False, allow_blank=True)


class PriceCalculateSerializer(serializers.Serializer):
    performance = serializers.IntegerField(required=False)
    bundle = serializers.IntegerField(required=False)
    quantity = serializers.IntegerField(min_value=1, max_value=10)
    discount_id = serializers.IntegerField(required=False, allow_null=True)

    def validate(self, attrs):
        if not attrs.get("performance") and not attrs.get("bundle"):
            raise serializers.ValidationError("必须指定场次或套票")
        if attrs.get("performance") and attrs.get("bundle"):
            raise serializers.ValidationError("不能同时指定场次和套票")
        return attrs


class PriceCalculateResultSerializer(serializers.Serializer):
    original_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    best_discount = DiscountDetailSerializer(required=False, allow_null=True)
    all_applicable_discounts = DiscountDetailSerializer(many=True)
    final_amount = serializers.DecimalField(max_digits=12, decimal_places=2)


class OrderSerializer(serializers.ModelSerializer):
    show_title = serializers.CharField(source="performance.show.title", read_only=True)
    bundle_name = serializers.CharField(source="bundle.name", read_only=True)
    discount_name = serializers.CharField(source="discount.name", read_only=True)

    class Meta:
        model = TicketOrder
        fields = [
            "id", "performance", "show_title", "bundle", "bundle_name",
            "discount", "discount_name", "customer_name", "phone",
            "quantity", "original_amount", "discount_amount", "amount",
            "status", "created_at",
        ]
        read_only_fields = ["id", "original_amount", "discount_amount", "amount", "status", "created_at"]


class OrderCreateSerializer(serializers.Serializer):
    performance = serializers.IntegerField()
    customer_name = serializers.CharField(max_length=64)
    phone = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")
    quantity = serializers.IntegerField(min_value=1, max_value=10)
    discount_id = serializers.IntegerField(required=False, allow_null=True)


class BundleOrderCreateSerializer(serializers.Serializer):
    bundle = serializers.IntegerField()
    customer_name = serializers.CharField(max_length=64)
    phone = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")
    quantity = serializers.IntegerField(min_value=1, max_value=10)
    discount_id = serializers.IntegerField(required=False, allow_null=True)


class BundleStatsSerializer(serializers.Serializer):
    bundle_id = serializers.IntegerField()
    bundle_name = serializers.CharField()
    total_sold = serializers.IntegerField()
    total_revenue = serializers.DecimalField(max_digits=12, decimal_places=2)


class DiscountStatsSerializer(serializers.Serializer):
    discount_id = serializers.IntegerField()
    discount_name = serializers.CharField()
    usage_count = serializers.IntegerField()
    total_discount_amount = serializers.DecimalField(max_digits=12, decimal_places=2)


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField()
