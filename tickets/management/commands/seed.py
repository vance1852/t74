"""初始化内置管理员与种子业务数据（幂等）。"""
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from tickets.models import Bundle, Discount, Performance, Show, TicketOrder


class Command(BaseCommand):
    help = "初始化管理员与演出票务种子数据"

    def handle(self, *args, **options):
        username = settings.DEFAULT_ADMIN_USERNAME
        password = settings.DEFAULT_ADMIN_PASSWORD
        if not User.objects.filter(username=username).exists():
            User.objects.create_superuser(username=username, password=password, first_name="平台管理员")
            self.stdout.write("已创建管理员账号")

        if Show.objects.exists():
            self.stdout.write("业务数据已存在，跳过")
            return

        shows = [
            Show.objects.create(title="星河巡回演唱会", troupe="星河乐团", genre="concert", status="on_sale"),
            Show.objects.create(title="金陵往事话剧", troupe="城南剧社", genre="drama", status="on_sale"),
            Show.objects.create(title="敦煌音乐剧", troupe="丝路艺术团", genre="musical", status="upcoming"),
            Show.objects.create(title="经典戏曲专场", troupe="梨园名家", genre="opera", status="ended"),
        ]

        now = datetime.now().replace(microsecond=0)
        perfs = [
            Performance.objects.create(show=shows[0], hall="一号厅", start_at=now + timedelta(days=3), total_seats=1200, sold_seats=860, price=380),
            Performance.objects.create(show=shows[0], hall="一号厅", start_at=now + timedelta(days=4), total_seats=1200, sold_seats=300, price=380),
            Performance.objects.create(show=shows[1], hall="小剧场", start_at=now + timedelta(days=2), total_seats=300, sold_seats=290, price=180),
            Performance.objects.create(show=shows[2], hall="大剧院", start_at=now + timedelta(days=20), total_seats=900, sold_seats=0, price=280),
        ]

        bundles = [
            Bundle.objects.create(
                name="星河演唱会双场联票",
                description="包含星河巡回演唱会两场演出，原价760，套票价680",
                price=680,
                is_active=True,
            ),
            Bundle.objects.create(
                name="戏剧爱好者套票",
                description="包含金陵往事话剧和星河演唱会各一场，原价560，套票价480",
                price=480,
                is_active=True,
            ),
        ]
        bundles[0].performances.set([perfs[0], perfs[1]])
        bundles[1].performances.set([perfs[0], perfs[2]])

        valid_from = now - timedelta(days=1)
        valid_to = now + timedelta(days=30)

        discounts = [
            Discount.objects.create(
                name="满300减50",
                discount_type="full_reduction",
                value=50,
                min_amount=300,
                valid_from=valid_from,
                valid_to=valid_to,
                is_active=True,
            ),
            Discount.objects.create(
                name="演唱会专享85折",
                discount_type="fixed",
                value=0.85,
                min_amount=0,
                valid_from=valid_from,
                valid_to=valid_to,
                is_active=True,
            ),
            Discount.objects.create(
                name="满1000减150",
                discount_type="full_reduction",
                value=150,
                min_amount=1000,
                valid_from=valid_from,
                valid_to=valid_to,
                is_active=True,
            ),
            Discount.objects.create(
                name="套票专享9折",
                discount_type="fixed",
                value=0.9,
                min_amount=0,
                valid_from=valid_from,
                valid_to=valid_to,
                is_active=True,
            ),
        ]
        discounts[1].applicable_performances.set([perfs[0], perfs[1]])
        discounts[3].applicable_bundles.set([bundles[0], bundles[1]])

        TicketOrder.objects.create(
            performance=perfs[0],
            bundle=None,
            discount=None,
            customer_name="陈静",
            phone="13900001111",
            quantity=2,
            original_amount=760,
            discount_amount=0,
            amount=760,
            status="paid",
        )
        TicketOrder.objects.create(
            performance=perfs[2],
            bundle=None,
            discount=None,
            customer_name="刘洋",
            phone="13900002222",
            quantity=4,
            original_amount=720,
            discount_amount=0,
            amount=720,
            status="paid",
        )
        TicketOrder.objects.create(
            performance=perfs[0],
            bundle=None,
            discount=None,
            customer_name="孙琳",
            phone="13900003333",
            quantity=1,
            original_amount=380,
            discount_amount=0,
            amount=380,
            status="cancelled",
        )

        self.stdout.write("种子数据初始化完成")
