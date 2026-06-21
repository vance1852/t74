from django.db import models
from django.db.models import Min


class Show(models.Model):
    """演出剧目。"""

    GENRE_CHOICES = [
        ("concert", "演唱会"),
        ("drama", "话剧"),
        ("musical", "音乐剧"),
        ("opera", "戏曲"),
        ("other", "其他"),
    ]
    STATUS_CHOICES = [
        ("on_sale", "售票中"),
        ("upcoming", "待开票"),
        ("ended", "已结束"),
    ]

    title = models.CharField(max_length=128)
    troupe = models.CharField(max_length=128, blank=True, default="")
    genre = models.CharField(max_length=16, choices=GENRE_CHOICES, default="concert")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="upcoming")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "shows"


class Performance(models.Model):
    """场次。"""

    show = models.ForeignKey(Show, on_delete=models.CASCADE, related_name="performances")
    hall = models.CharField(max_length=64, default="")
    start_at = models.DateTimeField()
    total_seats = models.IntegerField(default=0)
    sold_seats = models.IntegerField(default=0)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def remaining_seats(self):
        return self.total_seats - self.sold_seats

    class Meta:
        db_table = "performances"


class Bundle(models.Model):
    """套票产品。"""

    name = models.CharField(max_length=128)
    description = models.CharField(max_length=512, blank=True, default="")
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    performances = models.ManyToManyField(Performance, through="BundlePerformance", related_name="bundles")
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def available_stock(self):
        if not self.is_active:
            return 0
        perfs = self.performances.all()
        if not perfs:
            return 0
        remaining_stocks = [p.remaining_seats for p in perfs]
        return max(0, min(remaining_stocks))

    @property
    def is_sold_out(self):
        return self.available_stock == 0

    class Meta:
        db_table = "bundles"


class BundlePerformance(models.Model):
    """套票包含的场次关联。"""

    bundle = models.ForeignKey(Bundle, on_delete=models.CASCADE, related_name="bundle_performances")
    performance = models.ForeignKey(Performance, on_delete=models.CASCADE, related_name="bundle_performances")

    class Meta:
        db_table = "bundle_performances"
        unique_together = ["bundle", "performance"]


class Discount(models.Model):
    """优惠规则。"""

    TYPE_CHOICES = [
        ("fixed", "固定折扣"),
        ("full_reduction", "满减"),
    ]

    name = models.CharField(max_length=128)
    discount_type = models.CharField(max_length=16, choices=TYPE_CHOICES, default="fixed")
    value = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    min_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    valid_from = models.DateTimeField()
    valid_to = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    applicable_performances = models.ManyToManyField(Performance, through="DiscountPerformance", related_name="discounts", blank=True)
    applicable_bundles = models.ManyToManyField(Bundle, through="DiscountBundle", related_name="discounts", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "discounts"


class DiscountPerformance(models.Model):
    """优惠适用场次关联。"""

    discount = models.ForeignKey(Discount, on_delete=models.CASCADE, related_name="discount_performances")
    performance = models.ForeignKey(Performance, on_delete=models.CASCADE, related_name="discount_performances")

    class Meta:
        db_table = "discount_performances"
        unique_together = ["discount", "performance"]


class DiscountBundle(models.Model):
    """优惠适用套票关联。"""

    discount = models.ForeignKey(Discount, on_delete=models.CASCADE, related_name="discount_bundles")
    bundle = models.ForeignKey(Bundle, on_delete=models.CASCADE, related_name="discount_bundles")

    class Meta:
        db_table = "discount_bundles"
        unique_together = ["discount", "bundle"]


class TicketOrder(models.Model):
    """购票订单。"""

    STATUS_CHOICES = [
        ("paid", "已支付"),
        ("cancelled", "已取消"),
    ]

    performance = models.ForeignKey(Performance, on_delete=models.CASCADE, related_name="orders", null=True, blank=True)
    bundle = models.ForeignKey(Bundle, on_delete=models.CASCADE, related_name="orders", null=True, blank=True)
    discount = models.ForeignKey(Discount, on_delete=models.SET_NULL, related_name="orders", null=True, blank=True)
    customer_name = models.CharField(max_length=64)
    phone = models.CharField(max_length=32, blank=True, default="")
    quantity = models.IntegerField(default=1)
    original_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="paid")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ticket_orders"
