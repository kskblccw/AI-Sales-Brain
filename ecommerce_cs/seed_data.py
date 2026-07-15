"""
seed_data.py — 初始化模拟数据 + 构建 Chroma 知识库

用法：
    python seed_data.py          # 首次运行：建表 + 插入数据
    python seed_data.py --reset  # 重置所有数据
"""

import sys
import random
from datetime import datetime, timedelta

from config import DB_URL_SYNC
from database import (
    Base, User, Product, Order, OrderItem, ReturnRequest, FAQ,
    OrderStatus,
)


def seed():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    engine = create_engine(DB_URL_SYNC, echo=False)
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        if db.query(User).count() > 0:
            print("数据库已有数据，跳过插入。（使用 --reset 重置）")
            return

        # ═══════════════════════════════════════════════════════════════════
        # 用户 (20人)
        # ═══════════════════════════════════════════════════════════════════
        users = [
            User(name="张伟",   email="zhangwei@qq.com",    phone="13800001001"),
            User(name="李娜",   email="lina@qq.com",        phone="13800001002"),
            User(name="王强",   email="wangqiang@qq.com",   phone="13800001003"),
            User(name="赵敏",   email="zhaomin@qq.com",     phone="13800001004"),
            User(name="刘洋",   email="liuyang@qq.com",     phone="13800001005"),
            User(name="陈静",   email="chenjing@qq.com",    phone="13800001006"),
            User(name="孙磊",   email="sunlei@qq.com",      phone="13800001007"),
            User(name="周婷",   email="zhouting@qq.com",    phone="13800001008"),
            User(name="吴昊",   email="wuhao@qq.com",       phone="13800001009"),
            User(name="黄丽",   email="huangli@qq.com",     phone="13800001010"),
            User(name="马超",   email="machao@163.com",     phone="13900002001"),
            User(name="林黛玉", email="lindaiyu@163.com",   phone="13900002002"),
            User(name="郭靖",   email="guojing@163.com",    phone="13900002003"),
            User(name="杨过",   email="yangguo@163.com",    phone="13900002004"),
            User(name="小龙女", email="xiaolongnv@163.com", phone="13900002005"),
            User(name="张三丰", email="zhangsanfeng@163.com", phone="13900002006"),
            User(name="令狐冲", email="linghuchong@163.com", phone="13900002007"),
            User(name="任盈盈", email="renyingying@163.com", phone="13900002008"),
            User(name="韦小宝", email="weixiaobao@163.com", phone="13900002009"),
            User(name="康熙",   email="kangxi@163.com",     phone="13900002010"),
        ]
        db.add_all(users)
        db.flush()

        # ═══════════════════════════════════════════════════════════════════
        # 商品 (50个)
        # ═══════════════════════════════════════════════════════════════════
        products = [
            # ── 手机数码 (10) ──
            Product(name="iPhone 15 Pro Max 256GB", description="Apple A17 Pro芯片，钛金属，4800万像素主摄，USB-C接口，灵动岛交互。", price=9999, stock=85, category="手机数码",
                    specs={"品牌":"Apple","颜色":"原色钛金属","存储":"256GB","屏幕":"6.7英寸 OLED"}),
            Product(name="华为 Mate 60 Pro 512GB", description="麒麟9000S芯片，卫星通话，超可靠玄武架构，XMAGE影像系统，88W快充。", price=6999, stock=52, category="手机数码",
                    specs={"品牌":"华为","颜色":"雅丹黑","存储":"512GB","屏幕":"6.82英寸 OLED"}),
            Product(name="小米14 Ultra 512GB", description="骁龙8 Gen3，徕卡光学Summilux镜头，1英寸大底，90W有线+80W无线。", price=5999, stock=38, category="手机数码",
                    specs={"品牌":"小米","颜色":"陶瓷白","存储":"512GB","屏幕":"6.73英寸 AMOLED"}),
            Product(name="Samsung Galaxy S24 Ultra", description="钛金属边框，Galaxy AI，2亿像素，S Pen，5000mAh电池。", price=9699, stock=45, category="手机数码",
                    specs={"品牌":"Samsung","颜色":"钛灰色","存储":"256GB","屏幕":"6.8英寸 Dynamic AMOLED"}),
            Product(name="OPPO Find X7 Ultra", description="双潜望四摄，哈苏人像，骁龙8 Gen3，100W超级闪充。", price=5999, stock=30, category="手机数码",
                    specs={"品牌":"OPPO","颜色":"海阔天空","存储":"256GB","屏幕":"6.82英寸 AMOLED"}),
            Product(name="vivo X100 Pro", description="蔡司APO超级长焦，天玑9300，120W闪充，IP68防水。", price=4999, stock=42, category="手机数码",
                    specs={"品牌":"vivo","颜色":"星迹蓝","存储":"256GB","屏幕":"6.78英寸 AMOLED"}),
            Product(name="AirPods Pro 第二代", description="H2芯片，自适应音频，个性化空间音频，USB-C充电盒，6小时续航。", price=1899, stock=200, category="手机数码",
                    specs={"品牌":"Apple","类型":"入耳式","连接":"蓝牙5.3","续航":"6小时","降噪":"主动降噪"}),
            Product(name="华为 FreeBuds Pro 3", description="星闪连接，智慧动态降噪3.0，高清空间音频，离线查找。", price=1499, stock=88, category="手机数码",
                    specs={"品牌":"华为","类型":"入耳式","连接":"星闪/蓝牙","续航":"6.5小时"}),
            Product(name="Apple Watch Ultra 2", description="S9芯片，精确查找iPhone，双频GPS，100米防水，36小时续航。", price=6499, stock=25, category="手机数码",
                    specs={"品牌":"Apple","尺寸":"49mm","屏幕":"LTPO OLED","续航":"36小时","防水":"100米"}),
            Product(name="iPad Pro M4 11英寸", description="M4芯片，Ultra Retina XDR，Apple Pencil Pro，轻薄设计。", price=8999, stock=20, category="手机数码",
                    specs={"品牌":"Apple","芯片":"M4","存储":"256GB","屏幕":"11英寸 XDR"}),

            # ── 电脑办公 (10) ──
            Product(name="MacBook Pro 14英寸 M3 Pro", description="M3 Pro芯片，18GB统一内存，Liquid Retina XDR，18小时续航。", price=14999, stock=30, category="电脑办公",
                    specs={"品牌":"Apple","芯片":"M3 Pro","内存":"18GB","硬盘":"512GB","屏幕":"14.2英寸"}),
            Product(name="ThinkPad X1 Carbon Gen 12", description="Ultra 7 155H，14英寸2.8K OLED，仅重1.09kg，32GB内存。", price=10999, stock=22, category="电脑办公",
                    specs={"品牌":"Lenovo","处理器":"Ultra 7 155H","内存":"32GB","硬盘":"1TB","屏幕":"14英寸 OLED"}),
            Product(name="华为 MateBook X Pro 2024", description="Ultra 9 185H，3.1K OLED触控屏，仅重980g，超级快充。", price=11999, stock=18, category="电脑办公",
                    specs={"品牌":"华为","处理器":"Ultra 9 185H","内存":"32GB","硬盘":"1TB","屏幕":"14.2英寸 OLED"}),
            Product(name="Dell XPS 16", description="Ultra 9 185H，RTX 4070，4K+ OLED，铝合金机身。", price=16999, stock=10, category="电脑办公",
                    specs={"品牌":"Dell","处理器":"Ultra 9 185H","显卡":"RTX 4070","内存":"32GB","屏幕":"16.3英寸 4K+"}),
            Product(name="Logitech MX Keys S 键盘", description="Perfect Stroke按键，智能背光，多设备切换，USB-C充电。", price=799, stock=150, category="电脑办公",
                    specs={"品牌":"Logitech","连接":"蓝牙/接收器","布局":"全尺寸","背光":"智能背光"}),
            Product(name="罗技 MX Master 3S 鼠标", description="8000DPI，MagSpeed电磁滚轮，静音按键，跨屏Flow。", price=699, stock=180, category="电脑办公",
                    specs={"品牌":"Logitech","连接":"蓝牙/接收器","DPI":"8000","续航":"70天"}),
            Product(name="Dell U2723QE 27英寸4K", description="IPS Black技术，4K分辨率，USB-C 90W供电，内置KVM。", price=3999, stock=15, category="电脑办公",
                    specs={"品牌":"Dell","尺寸":"27英寸","分辨率":"3840x2160","接口":"USB-C/HDMI/DP"}),
            Product(name="Samsung 990 Pro 2TB SSD", description="PCIe 4.0，读取7450MB/s，写入6900MB/s，游戏办公首选。", price=1299, stock=60, category="电脑办公",
                    specs={"品牌":"Samsung","容量":"2TB","接口":"M.2 NVMe","读取":"7450MB/s"}),
            Product(name="WD My Passport 5TB 移动硬盘", description="USB 3.2，256位AES加密，自动备份，轻薄便携。", price=899, stock=90, category="电脑办公",
                    specs={"品牌":"Western Digital","容量":"5TB","接口":"USB 3.2","加密":"AES 256"}),
            Product(name="明基 ScreenBar Halo 屏幕挂灯", description="无线遥控，自动调光，非对称光学，不反光。", price=1099, stock=70, category="电脑办公",
                    specs={"品牌":"BenQ","功率":"6.5W","色温":"2700K-6500K","安装":"重力枢轴夹"}),

            # ── 家用电器 (10) ──
            Product(name="戴森 V15 Detect 无绳吸尘器", description="激光探测微尘，压电传感器，LCD显示灰尘数据，240AW吸力。", price=4990, stock=40, category="家用电器",
                    specs={"品牌":"Dyson","功率":"240AW","续航":"60分钟","尘盒":"0.76L"}),
            Product(name="科沃斯 X2 Omni 扫地机器人", description="全能基站自清洁，8000Pa吸力，AI避障，热水洗拖布。", price=4999, stock=25, category="家用电器",
                    specs={"品牌":"科沃斯","吸力":"8000Pa","续航":"180分钟","导航":"dToF激光"}),
            Product(name="戴森 AM07 无叶风扇", description="Air Amplifier气流倍增，静音设计，遥控器，易清洁。", price=3150, stock=35, category="家用电器",
                    specs={"品牌":"Dyson","类型":"无叶风扇","风速":"10档","遥控":"磁吸遥控"}),
            Product(name="飞利浦空气炸锅 HD9867", description="Rapid Air技术，减少90%油脂，7.3L大容量，智能烹饪。", price=1999, stock=60, category="家用电器",
                    specs={"品牌":"飞利浦","容量":"7.3L","功率":"2225W","温控":"数字触控"}),
            Product(name="小米净水器 H1000G", description="1000G大通量，双RO反渗透，智能水龙头，3:1纯废水比。", price=2999, stock=35, category="家用电器",
                    specs={"品牌":"小米","通量":"1000G","过滤":"双RO","废水比":"3:1"}),
            Product(name="美的变频空调 1.5匹", description="新一级能效，自清洁，WiFi智控，静音18dB。", price=3299, stock=55, category="家用电器",
                    specs={"品牌":"美的","匹数":"1.5匹","能效":"一级","噪音":"18dB(A)"}),
            Product(name="海尔 10公斤洗烘一体机", description="直驱变频，智能投放，空气洗，蒸汽除菌，WiFi智控。", price=4999, stock=20, category="家用电器",
                    specs={"品牌":"海尔","容量":"10kg","类型":"洗烘一体","电机":"直驱变频"}),
            Product(name="松下 嵌入式洗碗机 NP-TH1", description="扇形水流，80℃高温除菌，软水系统，独立烘干。", price=5980, stock=12, category="家用电器",
                    specs={"品牌":"松下","类型":"嵌入式","容量":"6套","烘干":"独立烘干"}),
            Product(name="追觅 H30 Ultra 洗地机", description="热水自清洁，18000Pa吸力，双侧贴边，60分钟续航。", price=4299, stock=28, category="家用电器",
                    specs={"品牌":"追觅","吸力":"18000Pa","续航":"60分钟","自清洁":"热水"}),
            Product(name="大宇 迷你折叠洗衣机", description="紫外线杀菌，折叠收纳，6L容量，适合内衣/婴儿衣物。", price=699, stock=100, category="家用电器",
                    specs={"品牌":"大宇","容量":"6L","杀菌":"紫外线","折叠":"是"}),

            # ── 服饰鞋包 (10) ──
            Product(name="Nike Air Zoom Pegasus 40 跑鞋", description="Zoom Air气垫，Flywire飞线，透气网面，经典跑鞋。", price=899, stock=120, category="服饰鞋包",
                    specs={"品牌":"Nike","类型":"跑鞋","鞋面":"网面","尺码":"39-46"}),
            Product(name="Adidas Ultraboost 23 跑鞋", description="BOOST中底，Primeknit+编织鞋面，Continental橡胶外底。", price=1299, stock=75, category="服饰鞋包",
                    specs={"品牌":"Adidas","类型":"跑鞋","中底":"BOOST","尺码":"38-45"}),
            Product(name="Herschel Little America 双肩包", description="25L大容量，15英寸笔记本隔层，磁吸扣+抽绳设计。", price=798, stock=90, category="服饰鞋包",
                    specs={"品牌":"Herschel","容量":"25L","材质":"Polyester","颜色":"黑色/灰色"}),
            Product(name="优衣库 无缝羽绒服 男款", description="高级轻型羽绒，无缝工艺防钻绒，轻量保暖，可收纳。", price=699, stock=200, category="服饰鞋包",
                    specs={"品牌":"优衣库","填充":"90%羽绒","重量":"约280g","尺码":"S-XXL"}),
            Product(name="Samsonite Winfield 3 28寸行李箱", description="PC硬壳，TSA密码锁，双排万向轮，扩展容量。", price=1999, stock=30, category="服饰鞋包",
                    specs={"品牌":"Samsonite","尺寸":"28寸","材质":"PC","重量":"4.5kg"}),
            Product(name="始祖鸟 Beta AR 冲锋衣", description="GORE-TEX Pro防水透气，可兼容头盔风帽，轻量耐磨。", price=5400, stock=15, category="服饰鞋包",
                    specs={"品牌":"Arc'teryx","面料":"GORE-TEX Pro","防水":"是","尺码":"S-XXL"}),
            Product(name="FILA 斐乐 老爹鞋 男女同款", description="复古潮流，增高厚底，透气网面，情侣鞋。", price=699, stock=110, category="服饰鞋包",
                    specs={"品牌":"FILA","类型":"休闲鞋","鞋底":"厚底增高","尺码":"36-44"}),
            Product(name="Coach 经典标志托特包", description="PVC配皮，拉链开合，大容量通勤，经典C logo。", price=2599, stock=40, category="服饰鞋包",
                    specs={"品牌":"Coach","材质":"PVC配皮","类型":"托特包","尺寸":"33x26x14cm"}),
            Product(name="蕉下 防晒衣 男女同款", description="UPF50+，冰丝面料凉感，全脸防护，轻薄透气。", price=299, stock=300, category="服饰鞋包",
                    specs={"品牌":"蕉下","防晒":"UPF50+","面料":"冰丝","尺码":"M-3XL"}),
            Product(name="New Balance 574 经典复古鞋", description="ENCAP缓震，麂皮+网面拼接，经典配色，四季百搭。", price=769, stock=85, category="服饰鞋包",
                    specs={"品牌":"New Balance","类型":"复古鞋","中底":"ENCAP","尺码":"36-45"}),

            # ── 食品生鲜 (10) ──
            Product(name="三只松鼠 坚果大礼包 2.5kg", description="夏威夷果、腰果、巴旦木等10种坚果组合，每日坚果。", price=199, stock=500, category="食品生鲜",
                    specs={"品牌":"三只松鼠","重量":"2.5kg","种类":"10种","保质期":"240天"}),
            Product(name="蒙牛 特仑苏纯牛奶 250ml×24盒", description="3.6g蛋白质，甄选牧场，利乐钻包装，早餐必备。", price=89, stock=300, category="食品生鲜",
                    specs={"品牌":"蒙牛","规格":"250ml×24","蛋白质":"3.6g/100ml","保质期":"6个月"}),
            Product(name="澳洲安格斯谷饲牛排 1kg", description="谷饲200天，雪花纹理，冷冻锁鲜，约4-5片。", price=168, stock=80, category="食品生鲜",
                    specs={"品牌":"澳洲进口","规格":"1kg","部位":"西冷/肉眼","储存":"-18℃冷冻"}),
            Product(name="农夫山泉 东方树叶茉莉花茶 500ml×15", description="0糖0卡，冷萃工艺，清爽解腻，整箱装。", price=69, stock=400, category="食品生鲜",
                    specs={"品牌":"农夫山泉","规格":"500ml×15","糖分":"0g","类型":"茉莉花茶"}),
            Product(name="良品铺子 每日坚果 30包混合装", description="6种坚果果干科学配比，独立小包装，30天量。", price=139, stock=250, category="食品生鲜",
                    specs={"品牌":"良品铺子","规格":"25g×30包","种类":"6种","保质期":"180天"}),
            Product(name="瑞士莲 特醇黑巧 70% 100g×3", description="瑞士进口，70%可可，丝滑口感，无添加。", price=108, stock=200, category="食品生鲜",
                    specs={"品牌":"瑞士莲","可可含量":"70%","规格":"100g×3","产地":"瑞士"}),
            Product(name="五常大米 稻花香2号 5kg", description="东北五常产地直供，2024新米，香糯可口。", price=79, stock=350, category="食品生鲜",
                    specs={"品牌":"五常","产地":"黑龙江五常","规格":"5kg","品种":"稻花香2号"}),
            Product(name="认养一头牛 酸奶 200g×12盒", description="自有牧场，生牛乳发酵，零添加，浓稠顺滑。", price=69, stock=250, category="食品生鲜",
                    specs={"品牌":"认养一头牛","规格":"200g×12","类型":"原味酸奶","储存":"冷藏"}),
            Product(name="百草味 手撕鱿鱼条 500g", description="深海捕捞，手工撕制，肉质厚实，追剧零食。", price=49, stock=400, category="食品生鲜",
                    specs={"品牌":"百草味","规格":"500g","口味":"原味/香辣","保质期":"12个月"}),
            Product(name="RIO 锐澳 微醺鸡尾酒 330ml×8罐", description="3度微醺，多种口味，低糖低卡，派对必备。", price=59, stock=300, category="食品生鲜",
                    specs={"品牌":"RIO","规格":"330ml×8","酒精度":"3%","口味":"混合装"}),
        ]
        db.add_all(products)
        db.flush()

        # ═══════════════════════════════════════════════════════════════════
        # 订单 (30个)
        # ═══════════════════════════════════════════════════════════════════
        statuses = [OrderStatus.SHIPPED] * 8 + [OrderStatus.COMPLETED] * 10 + [OrderStatus.PENDING] * 6 + [OrderStatus.CANCELLED] * 4 + [OrderStatus.SHIPPED] * 2
        addresses = [
            "北京市朝阳区建国路88号 SOHO现代城A座1201",
            "上海市浦东新区陆家嘴环路1000号 恒生银行大厦15F",
            "广州市天河区体育西路111号 维多利广场B座2208",
            "深圳市南山区科技园南路2号 软件产业基地4栋A单元",
            "杭州市西湖区文三路456号 东部软件园科技大厦9层",
            "成都市武侯区人民南路四段19号 威斯顿联邦大厦7F",
            "南京市鼓楼区中山北路28号 江苏商厦1305",
            "武汉市洪山区珞喻路1037号 华中科技大学科技园",
            "西安市雁塔区长安南路300号 曲江文化大厦",
            "重庆市渝北区新南路166号 龙湖MOCO 2栋",
            "天津市和平区南京路128号 天津中心大厦",
            "长沙市岳麓区麓谷大道600号 中电软件园",
        ]

        for i in range(30):
            user_idx = i % len(users)
            status = statuses[i % len(statuses)]
            items_count = random.randint(1, 4)
            product_ids = random.sample([p.id for p in products], items_count)

            items_data = []
            total = 0
            for pid in product_ids:
                qty = random.randint(1, 3)
                prod = db.get(Product, pid)
                items_data.append((pid, qty, prod.price))
                total += prod.price * qty

            # 物流号生成
            carriers = ["SF", "YT", "ZTO", "JD", "DB"]
            carrier = carriers[i % len(carriers)]
            tracking = f"{carrier}{random.randint(1000000000, 9999999999)}" if status in [OrderStatus.SHIPPED, OrderStatus.COMPLETED] else None

            order = Order(
                order_no=f"ORD{datetime.now().strftime('%Y%m%d')}{i+1:04d}",
                user_id=users[user_idx].id,
                status=status,
                total=round(total, 2),
                address=addresses[i % len(addresses)],
                tracking_no=tracking,
                created_at=datetime.now() - timedelta(days=random.randint(1, 90)),
            )
            db.add(order)
            db.flush()

            for pid, qty, price in items_data:
                db.add(OrderItem(order_id=order.id, product_id=pid, quantity=qty, unit_price=price))

        # ═══════════════════════════════════════════════════════════════════
        # FAQ (25条)
        # ═══════════════════════════════════════════════════════════════════
        faqs = [
            # 配送物流
            FAQ(question="下单后多久发货？", answer="一般情况下，下单后24小时内发货。工作日15:00前下单当天发出，15:00后次日发出。节假日顺延。", category="配送物流"),
            FAQ(question="配送需要多少天？", answer="全国主要城市1-3天送达。一线城市次日达，二线城市2-3天，三四线城市3-5天。顺丰加急可次日达。偏远地区（新疆、西藏等）5-7天。", category="配送物流"),
            FAQ(question="如何查询物流信息？", answer="登录账户后在「我的订单」点击对应订单查看物流详情。也可复制运单号到快递官网（顺丰/圆通/中通/京东/德邦）查询。", category="配送物流"),
            FAQ(question="能否指定配送时间？", answer="部分城市支持精准达服务，可指定配送时段（9:00-12:00、14:00-18:00等）。下单时选择即可，会产生5-10元的额外服务费。", category="配送物流"),
            FAQ(question="海外地区能否配送？", answer="目前支持港澳台配送，运费按重量计算，预计5-10个工作日。暂不支持其他海外地区配送。", category="配送物流"),
            FAQ(question="下单后可以修改收货地址吗？", answer="订单未发货时可在订单详情页修改地址。已发货订单无法修改地址，可联系快递公司转寄（可能产生费用）。", category="配送物流"),

            # 售后政策
            FAQ(question="退换货政策是什么？", answer="7天无理由退货（商品完好、不影响二次销售）。15天内质量问题的可换货。退货由买家承担运费（质量问题由平台承担）。生鲜食品、个人护理、定制商品不支持无理由退货。", category="售后政策"),
            FAQ(question="如何申请退货？", answer="进入「我的订单」，找到需退货的订单，点击「申请售后」选择退货类型和填写原因。客服审核通过后发送退货地址，寄回商品后仓库质检，1-3个工作日完成退款。", category="售后政策"),
            FAQ(question="退款什么时候到账？", answer="收到退货后1-3个工作日完成质检，确认无误后立即退款。支付宝/微信即时到账，银行卡1-3个工作日，信用卡3-7个工作日（视发卡行而定）。", category="售后政策"),
            FAQ(question="商品价格保护政策？", answer="自下单之日起7天内，如商品降价可申请价保。联系客服提供订单号和降价截图，审核通过后差价原路返还。秒杀/拼团/限时抢购商品不参与价保。", category="售后政策"),
            FAQ(question="收到商品有质量问题怎么办？", answer="签收后如发现质量问题，请拍照保存证据，24小时内联系客服。经核实后可以：换新、退货退款、部分退款补偿。运费由平台承担。", category="售后政策"),
            FAQ(question="换货的流程是什么？", answer="联系客服说明换货原因→提交换货申请→审核通过后寄回商品→仓库收到后发新货。换货一般在3-5个工作日内完成。", category="售后政策"),

            # 支付相关
            FAQ(question="支持哪些支付方式？", answer="支持：支付宝/微信支付/银联卡/Apple Pay/花呗分期（3/6/12期）/京东白条/云闪付。部分商品支持货到付款（仅限现金或pos刷卡）。", category="支付相关"),
            FAQ(question="如何申请分期付款？", answer="下单时在支付方式选择「花呗分期」或「信用卡分期」，可选3/6/12期。分期手续费：3期免息、6期0.6%/期、12期0.5%/期。", category="支付相关"),
            FAQ(question="支付失败怎么办？", answer="检查：银行卡余额是否充足/是否超出单笔限额/网络是否稳定。也可尝试更换支付方式或清除App缓存后重试。如仍有问题请联系客服。", category="支付相关"),

            # 会员权益
            FAQ(question="会员有什么权益？", answer="银卡98折、金卡95折、钻石9折。积分可抵扣现金（100积分=1元），生日当月双倍积分。专属客服、优先发货、免费退货等权益逐级解锁。", category="会员权益"),
            FAQ(question="如何升级会员等级？", answer="年消费满2000元升级金卡、满5000元升级钻石卡。每年1月1日根据上年消费重新评定。升级后即时生效，有效期至当年12月31日。", category="会员权益"),
            FAQ(question="积分如何获取和使用？", answer="消费1元=1积分。积分可用于：抵扣现金（100积分=1元）、兑换优惠券、兑换商品。积分有效期为获得之日起1年。", category="会员权益"),

            # 订单相关
            FAQ(question="如何取消订单？", answer="订单未发货时可在订单详情页直接取消，款项即时退回。已发货订单无法直接取消，可在收货后申请退货退款。", category="订单相关"),
            FAQ(question="发票如何开具？", answer="下单时可选择电子发票或纸质发票。电子发票在确认收货后自动发送至邮箱。纸质发票随包裹寄出。支持个人抬头和公司抬头（需提供税号）。", category="订单相关"),
            FAQ(question="可以修改订单中的商品吗？", answer="订单未发货时可以取消重下。已发货订单无法修改商品。如需增加商品建议单独下单。", category="订单相关"),

            # 其他
            FAQ(question="如何联系人工客服？", answer="在线客服时间：每天9:00-22:00。客服热线：400-888-8888（工作日9:00-18:00）。紧急问题可发邮件至service@shop.com。智能客服7×24小时在线。", category="其他"),
            FAQ(question="你们的营业时间是？", answer="在线客服每天9:00-22:00。订单系统7×24小时运行，随时可下单。仓库发货时间为工作日9:00-18:00。", category="其他"),
            FAQ(question="企业团购有优惠吗？", answer="企业团购（单笔≥50件或金额≥5000元）可享受额外折扣。请联系企业客服专线：400-888-9999 或邮件至corp@shop.com。", category="其他"),
            FAQ(question="如何成为平台的供应商/商家？", answer="请访问商家入驻页面填写申请，或发送合作意向至partner@shop.com。审核团队将在3个工作日内回复。", category="其他"),
        ]
        db.add_all(faqs)

        db.commit()
        print(f"[Seed] 完成: {len(users)}用户 {len(products)}商品 30订单 {len(faqs)}FAQ")


if __name__ == "__main__":
    reset = "--reset" in sys.argv
    if reset:
        from sqlalchemy import create_engine
        engine = create_engine(DB_URL_SYNC, echo=False)
        Base.metadata.drop_all(engine)
        print("旧数据已清除。")

    seed()
    print("[OK] 数据初始化完毕！")
