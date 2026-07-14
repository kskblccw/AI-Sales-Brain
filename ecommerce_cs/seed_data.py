"""
seed_data.py — 初始化模拟数据 + 构建 Chroma 知识库

用法：
    python seed_data.py          # 首次运行：建表 + 插入数据 + 构建 RAG
    python seed_data.py --reset  # 重置所有数据
"""

import sys
import asyncio
import random
from datetime import datetime, timedelta

from config import DB_URL_SYNC
from database import (
    Base, User, Product, Order, OrderItem, ReturnRequest, FAQ,
    OrderStatus,
)


def seed():
    """同步方式插入种子数据"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    engine = create_engine(DB_URL_SYNC, echo=False)

    # 建表
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        # 已有数据则跳过
        if db.query(User).count() > 0:
            print("数据库已有数据，跳过插入。（使用 --reset 重置）")
            return

        # ── 用户 ────────────────────────────────────────────────────────────
        users = [
            User(name="张伟", email="zhangwei@qq.com", phone="13800001001"),
            User(name="李娜", email="lina@qq.com", phone="13800001002"),
            User(name="王强", email="wangqiang@qq.com", phone="13800001003"),
            User(name="赵敏", email="zhaomin@qq.com", phone="13800001004"),
            User(name="刘洋", email="liuyang@qq.com", phone="13800001005"),
            User(name="陈静", email="chenjing@qq.com", phone="13800001006"),
            User(name="孙磊", email="sunlei@qq.com", phone="13800001007"),
            User(name="周婷", email="zhouting@qq.com", phone="13800001008"),
            User(name="吴昊", email="wuhao@qq.com", phone="13800001009"),
            User(name="黄丽", email="huangli@qq.com", phone="13800001010"),
        ]
        db.add_all(users)
        db.flush()

        # ── 商品 ────────────────────────────────────────────────────────────
        products = [
            # 手机数码
            Product(name="iPhone 15 Pro Max 256GB", description="苹果最新旗舰手机，A17 Pro芯片，钛金属设计，4800万像素主摄，支持USB-C接口。", price=9999, stock=85, category="手机数码",
                    specs={"品牌": "Apple", "颜色": "原色钛金属", "存储": "256GB", "屏幕": "6.7英寸"}, image_url="📱"),
            Product(name="华为 Mate 60 Pro", description="华为旗舰手机，麒麟9000S芯片，卫星通话功能，超可靠玄武架构，XMAGE影像。", price=6999, stock=52, category="手机数码",
                    specs={"品牌": "华为", "颜色": "雅丹黑", "存储": "512GB", "屏幕": "6.82英寸"}, image_url="📱"),
            Product(name="AirPods Pro 第二代", description="Apple 主动降噪无线耳机，H2芯片，自适应音频，个性化空间音频，USB-C充电盒。", price=1899, stock=200, category="手机数码",
                    specs={"品牌": "Apple", "类型": "入耳式", "连接": "蓝牙5.3", "续航": "6小时"}, image_url="🎧"),
            Product(name="小米14 Ultra", description="小米旗舰，骁龙8 Gen3，徕卡光学，Summilux镜头，1英寸大底主摄。", price=5999, stock=38, category="手机数码",
                    specs={"品牌": "小米", "颜色": "陶瓷白", "存储": "512GB", "屏幕": "6.73英寸"}, image_url="📱"),
            Product(name="Samsung Galaxy S24 Ultra", description="三星旗舰，钛金属边框，AI智能，2亿像素，S Pen支持。", price=9699, stock=45, category="手机数码",
                    specs={"品牌": "Samsung", "颜色": "钛灰色", "存储": "256GB", "屏幕": "6.8英寸"}, image_url="📱"),

            # 电脑办公
            Product(name="MacBook Pro 14英寸 M3 Pro", description="Apple M3 Pro芯片，18GB统一内存，Liquid Retina XDR显示屏，18小时续航。", price=14999, stock=30, category="电脑办公",
                    specs={"品牌": "Apple", "芯片": "M3 Pro", "内存": "18GB", "硬盘": "512GB"}, image_url="💻"),
            Product(name="ThinkPad X1 Carbon Gen 11", description="联想商务旗舰，i7-1365U，14英寸2.8K OLED屏，仅重1.12kg。", price=10999, stock=22, category="电脑办公",
                    specs={"品牌": "Lenovo", "处理器": "i7-1365U", "内存": "32GB", "硬盘": "1TB"}, image_url="💻"),
            Product(name="Logitech MX Keys S 无线键盘", description="罗技高端无线键盘，Perfect Stroke按键，智能背光，多设备切换，USB-C充电。", price=799, stock=150, category="电脑办公",
                    specs={"品牌": "Logitech", "连接": "蓝牙/接收器", "布局": "全尺寸", "背光": "智能背光"}, image_url="⌨️"),
            Product(name="Dell U2723QE 27英寸4K显示器", description="戴尔专业显示器，4K分辨率，IPS Black技术，USB-C 90W供电，内置KVM。", price=3999, stock=18, category="电脑办公",
                    specs={"品牌": "Dell", "尺寸": "27英寸", "分辨率": "3840x2160", "接口": "USB-C/HDMI/DP"}, image_url="🖥️"),
            Product(name="罗技 MX Master 3S 鼠标", description="罗技旗舰鼠标，8000DPI，MagSpeed滚轮，静音按键，Flow跨屏控制。", price=699, stock=180, category="电脑办公",
                    specs={"品牌": "Logitech", "连接": "蓝牙/接收器", "DPI": "8000", "续航": "70天"}, image_url="🖱️"),

            # 家用电器
            Product(name="戴森 V15 Detect 无绳吸尘器", description="戴森旗舰吸尘器，激光探测微尘，压电式传感器，LCD屏幕实时显示灰尘数据。", price=4990, stock=40, category="家用电器",
                    specs={"品牌": "Dyson", "功率": "240AW", "续航": "60分钟", "尘盒": "0.76L"}, image_url="🧹"),
            Product(name="科沃斯 X2 Omni 扫地机器人", description="科沃斯旗舰扫地机器人，全能基站自清洁，8000Pa吸力，AI避障，拖布自清洁。", price=4999, stock=25, category="家用电器",
                    specs={"品牌": "科沃斯", "吸力": "8000Pa", "续航": "180分钟", "导航": "dToF激光"}, image_url="🤖"),
            Product(name="飞利浦空气炸锅 HD9867", description="飞利浦旗舰空气炸锅，Rapid Air技术，减少90%油脂，7.3L大容量，智能烹饪程序。", price=1999, stock=60, category="家用电器",
                    specs={"品牌": "飞利浦", "容量": "7.3L", "功率": "2225W", "温控": "数字触控"}, image_url="🍟"),
            Product(name="小米净水器 H1000G", description="小米厨下式净水器，1000G大通量，双RO反渗透，智能水龙头，App水质监控。", price=2999, stock=35, category="家用电器",
                    specs={"品牌": "小米", "通量": "1000G", "过滤": "双RO", "废水比": "3:1"}, image_url="💧"),
            Product(name="美的变频空调 1.5匹", description="美的新一级能效变频空调，自清洁，WiFi智控，静音18dB，快速冷暖。", price=3299, stock=55, category="家用电器",
                    specs={"品牌": "美的", "匹数": "1.5匹", "能效": "一级", "噪音": "18dB"}, image_url="❄️"),

            # 服饰鞋包
            Product(name="Nike Air Zoom Pegasus 40 男款跑鞋", description="耐克经典跑鞋，Zoom Air气垫，Flywire飞线技术，透气网面，适合日常跑步。", price=899, stock=120, category="服饰鞋包",
                    specs={"品牌": "Nike", "类型": "跑鞋", "鞋面": "网面", "尺码": "39-46"}, image_url="👟"),
            Product(name="Herschel Little America 双肩包", description="Herschel经典双肩包，25L大容量，15英寸笔记本隔层，磁吸扣+抽绳设计。", price=798, stock=90, category="服饰鞋包",
                    specs={"品牌": "Herschel", "容量": "25L", "材质": "Polyester", "颜色": "黑色/灰色"}, image_url="🎒"),
            Product(name="优衣库 无缝羽绒服 男款", description="优衣库高级轻型羽绒服，无缝工艺防钻绒，轻量保暖，可收纳设计。", price=699, stock=200, category="服饰鞋包",
                    specs={"品牌": "优衣库", "填充": "90%羽绒", "重量": "约280g", "尺码": "S-XXL"}, image_url="🧥"),
            Product(name="Adidas Ultraboost 23 跑鞋", description="Adidas顶级缓震跑鞋，BOOST中底，Primeknit+编织鞋面，Continental橡胶外底。", price=1299, stock=75, category="服饰鞋包",
                    specs={"品牌": "Adidas", "类型": "跑鞋", "中底": "BOOST", "尺码": "38-45"}, image_url="👟"),
            Product(name="Samsonite Winfield 3 行李箱 28寸", description="新秀丽硬壳行李箱，PC材质，TSA密码锁，双排万向轮，扩展容量。", price=1999, stock=30, category="服饰鞋包",
                    specs={"品牌": "Samsonite", "尺寸": "28寸", "材质": "PC", "重量": "4.5kg"}, image_url="🧳"),

            # 食品生鲜
            Product(name="三只松鼠 坚果大礼包 2.5kg", description="三只松鼠年货礼盒，含夏威夷果、腰果、巴旦木等10种坚果，每日坚果组合。", price=199, stock=500, category="食品生鲜",
                    specs={"品牌": "三只松鼠", "重量": "2.5kg", "种类": "10种", "保质期": "240天"}, image_url="🥜"),
            Product(name="蒙牛 特仑苏 纯牛奶 250ml×24盒", description="蒙牛特仑苏纯牛奶，3.6g蛋白质，甄选牧场，利乐钻包装。", price=89, stock=300, category="食品生鲜",
                    specs={"品牌": "蒙牛", "规格": "250ml×24", "蛋白质": "3.6g/100ml", "保质期": "6个月"}, image_url="🥛"),
            Product(name="澳洲进口 安格斯谷饲牛排 1kg", description="澳洲进口安格斯牛排，谷饲200天，雪花纹理，冷冻锁鲜，约4-5片。", price=168, stock=80, category="食品生鲜",
                    specs={"品牌": "澳洲进口", "规格": "1kg", "部位": "西冷/肉眼", "储存": "-18℃冷冻"}, image_url="🥩"),
            Product(name="农夫山泉 东方树叶 茉莉花茶 500ml×15", description="农夫山泉东方树叶，茉莉花茶饮料，0糖0卡，冷萃工艺，清爽解腻。", price=69, stock=400, category="食品生鲜",
                    specs={"品牌": "农夫山泉", "规格": "500ml×15", "糖分": "0g", "类型": "茉莉花茶"}, image_url="🍵"),
            Product(name="良品铺子 每日坚果 30包混合装", description="良品铺子每日坚果，6种坚果果干科学配比，独立小包装，30天量。", price=139, stock=250, category="食品生鲜",
                    specs={"品牌": "良品铺子", "规格": "25g×30包", "种类": "6种", "保质期": "180天"}, image_url="🥜"),
        ]
        db.add_all(products)
        db.flush()

        # ── 订单 ────────────────────────────────────────────────────────────
        statuses = [OrderStatus.SHIPPED, OrderStatus.SHIPPED, OrderStatus.COMPLETED,
                    OrderStatus.PENDING, OrderStatus.CANCELLED, OrderStatus.COMPLETED]
        carriers = ["顺丰速运", "中通快递", "圆通速递", "韵达快递", "京东物流"]
        addresses = [
            "北京市朝阳区建国路88号", "上海市浦东新区陆家嘴环路1000号",
            "广州市天河区体育西路111号", "深圳市南山区科技园南路2号",
            "杭州市西湖区文三路456号", "成都市武侯区人民南路四段19号",
        ]

        for i in range(15):
            user_idx = i % len(users)
            status = statuses[i % len(statuses)]
            tracking = f"{'SF' if i % 5 == 0 else 'YT' if i % 5 == 1 else 'ZTO' if i % 5 == 2 else 'YD' if i % 5 == 3 else 'JD'}{random.randint(10000000000, 99999999999)}"
            product_ids = random.sample([p.id for p in products], random.randint(1, 3))
            items_data = [(pid, random.randint(1, 3)) for pid in product_ids]
            total = sum(
                db.get(Product, pid).price * qty
                for pid, qty in items_data
            )
            addr = addresses[user_idx % len(addresses)]

            order = Order(
                order_no=f"ORD{datetime.now().strftime('%Y%m%d')}{i+1:04d}",
                user_id=users[user_idx].id,
                status=status,
                total=round(total, 2),
                address=addr,
                tracking_no=tracking if status in [OrderStatus.SHIPPED, OrderStatus.COMPLETED] else None,
                created_at=datetime.now() - timedelta(days=random.randint(1, 60)),
            )
            db.add(order)
            db.flush()

            for pid, qty in items_data:
                prod = db.get(Product, pid)
                db.add(OrderItem(order_id=order.id, product_id=pid, quantity=qty, unit_price=prod.price))

        # ── FAQ ──────────────────────────────────────────────────────────────
        faqs = [
            FAQ(question="下单后多久发货？", answer="一般情况下，下单后24小时内发货。工作日15:00前下单当天发出，15:00后次日发出。节假日顺延。", category="配送物流"),
            FAQ(question="配送需要多少天？", answer="全国大部分地区1-3天送达。具体时效：一线城市1-2天，二线城市2-3天，三四线城市3-5天。顺丰加急可次日达。", category="配送物流"),
            FAQ(question="如何查询物流信息？", answer="登录账户后在「我的订单」中点击对应订单可查看物流详情。也可在订单详情页复制运单号到快递官网查询。", category="配送物流"),
            FAQ(question="退换货政策是什么？", answer="支持7天无理由退货（商品完好、不影响二次销售）。15天内如有质量问题可换货。退货运费由买家承担（质量问题除外）。", category="售后政策"),
            FAQ(question="如何申请退货？", answer="进入「我的订单」，找到需要退货的订单，点击「申请售后」选择退货类型并填写原因。客服审核通过后会发送退货地址。", category="售后政策"),
            FAQ(question="退款什么时候到账？", answer="收到退货后1-3个工作日完成质检，确认无误后立即退款。退款按原支付方式返回，支付宝/微信一般即时到账，银行卡1-3个工作日。", category="售后政策"),
            FAQ(question="支持哪些支付方式？", answer="支持支付宝、微信支付、银联卡、Apple Pay、花呗分期（3/6/12期）和白条支付。部分商品支持货到付款。", category="支付相关"),
            FAQ(question="如何修改或取消订单？", answer="订单未发货时可在订单详情页直接取消。已发货订单无法直接取消，可在收到货后申请退货退款。如需修改地址请及时联系客服。", category="订单相关"),
            FAQ(question="会员有什么权益？", answer="会员分为银卡/金卡/钻石三级。银卡享98折、金卡95折、钻石9折。积分可抵扣现金（100积分=1元），生日当月享双倍积分。", category="会员权益"),
            FAQ(question="如何注册会员？", answer="注册账号即成为银卡会员。年度消费满2000元升级金卡，满5000元升级钻石卡。会员等级每年1月1日根据上年消费金额重新评定。", category="会员权益"),
            FAQ(question="发票如何开具？", answer="下单时可选择开具电子发票或纸质发票。电子发票在确认收货后自动发送至注册邮箱。纸质发票随包裹寄出。支持个人和公司抬头。", category="订单相关"),
            FAQ(question="商品价格保护政策？", answer="自下单之日起7天内，如商品降价可申请价保。联系客服提供订单号和降价截图，审核通过后差价原路返还。秒杀/拼团商品不参与价保。", category="售后政策"),
            FAQ(question="能否指定配送时间？", answer="部分城市支持精准达服务，可指定配送时间段（如9:00-12:00、14:00-18:00等）。下单时在配送方式中选择即可，会产生额外费用约5-10元。", category="配送物流"),
            FAQ(question="海外地区能否配送？", answer="目前支持配送至港澳台地区，运费按重量计算。暂不支持其他海外地区配送。港澳台配送时效约5-10个工作日。", category="配送物流"),
            FAQ(question="如何联系人工客服？", answer="在线客服时间：每天9:00-22:00。也可拨打客服热线400-888-8888（工作日9:00-18:00）。紧急问题可发送邮件至service@shop.com。", category="其他"),
        ]
        db.add_all(faqs)

        db.commit()
        print(f"数据库初始化完成：{len(users)} 用户、{len(products)} 商品、15 订单、{len(faqs)} FAQ。")


if __name__ == "__main__":
    reset = "--reset" in sys.argv

    if reset:
        from sqlalchemy import create_engine
        engine = create_engine(DB_URL_SYNC, echo=False)
        Base.metadata.drop_all(engine)
        print("旧数据已清除。")

    seed()
    print("\n[OK] 数据初始化完毕！")
