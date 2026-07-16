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
        # 商品（200款，从 products_data.py 导入）
        # ═══════════════════════════════════════════════════════════════════
        from products_data import PRODUCTS
        products = [Product(
            name=p["name"], description=p["description"],
            price=p["price"], stock=p["stock"], category=p["category"],
            specs=p["specs"],
        ) for p in PRODUCTS]
        db.add_all(products)
        db.flush()

        # ═══════════════════════════════════════════════════════════════════
        # 订单 (50个)
        # ═══════════════════════════════════════════════════════════════════
        statuses = [OrderStatus.SHIPPED] * 14 + [OrderStatus.COMPLETED] * 16 + [OrderStatus.PENDING] * 10 + [OrderStatus.CANCELLED] * 6 + [OrderStatus.SHIPPED] * 4
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

        for i in range(50):
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
        # FAQ (43条)
        # ═══════════════════════════════════════════════════════════════════
        faqs = [
            # 配送物流
            FAQ(question="下单后多久发货？", answer="一般情况下，下单后24小时内发货。工作日15:00前下单当天发出，15:00后次日发出。节假日顺延。", category="配送物流"),
            FAQ(question="配送需要多少天？", answer="全国主要城市1-3天送达。一线城市次日达，二线城市2-3天，三四线城市3-5天。顺丰加急可次日达。偏远地区（新疆、西藏等）5-7天。", category="配送物流"),
            FAQ(question="如何查询物流信息？", answer="登录账户后在「我的订单」点击对应订单查看物流详情。也可复制运单号到快递官网（顺丰/圆通/中通/京东/德邦）查询。", category="配送物流"),
            FAQ(question="能否指定配送时间？", answer="部分城市支持精准达服务，可指定配送时段（9:00-12:00、14:00-18:00等）。下单时选择即可，会产生5-10元的额外服务费。", category="配送物流"),
            FAQ(question="海外地区能否配送？", answer="目前支持港澳台配送，运费按重量计算，预计5-10个工作日。暂不支持其他海外地区配送。", category="配送物流"),
            FAQ(question="下单后可以修改收货地址吗？", answer="订单未发货时可在订单详情页修改地址。已发货订单无法修改地址，可联系快递公司转寄（可能产生费用）。", category="配送物流"),
            FAQ(question="可以指定快递公司吗？", answer="默认根据地址和商品类型自动匹配最优快递。如需指定快递，下单时在备注中写明，可能产生5-20元额外费用。", category="配送物流"),
            FAQ(question="快递丢件怎么办？", answer="如快递超过预计时效3天未更新物流，请联系客服核实。确认丢件后全额退款或重新补发，由我们向快递公司索赔。", category="配送物流"),
            FAQ(question="可以自提吗？", answer="部分城市支持门店自提。下单时选择「到店自提」，商品到达后会短信通知，凭取货码7天内提取。", category="配送物流"),

            # 售后政策
            FAQ(question="退换货政策是什么？", answer="7天无理由退货（商品完好不影响二次销售）。15天内质量问题可换货。退货买家承担运费（质量问题平台承担）。生鲜食品、个人护理、定制商品不支持无理由退货。", category="售后政策"),
            FAQ(question="如何申请退货？", answer="进入「我的订单」，找到需退货的订单，点击「申请售后」选择退货类型和填写原因。客服审核通过后发退货地址，寄回后1-3个工作日完成退款。", category="售后政策"),
            FAQ(question="退款什么时候到账？", answer="收到退货后1-3个工作日完成质检，确认无误后立即退款。支付宝/微信即时到账，银行卡1-3个工作日，信用卡3-7个工作日。", category="售后政策"),
            FAQ(question="商品价格保护政策？", answer="自下单之日起7天内，如商品降价可申请价保。联系客服提供订单号和降价截图，审核通过后差价原路返还。秒杀/拼团/限时抢购商品不参与价保。", category="售后政策"),
            FAQ(question="收到商品有质量问题怎么办？", answer="签收后如发现质量问题，请拍照保存证据，24小时内联系客服。经核实后可以：换新、退货退款、部分退款补偿。运费由平台承担。", category="售后政策"),
            FAQ(question="换货的流程是什么？", answer="联系客服说明换货原因→提交换货申请→审核通过后寄回商品→仓库验收后发新货。换货一般3-5个工作日完成。", category="售后政策"),
            FAQ(question="换货需要多长时间？", answer="仓库收到退回商品后1-2个工作日验收，通过后当天发出新商品。整个换货流程通常3-5个工作日完成。", category="售后政策"),
            FAQ(question="退货后运费险怎么赔付？", answer="如购买了运费险（通常0.5-3元/单），退货后保险公司在签收退货后72小时内自动理赔到支付宝/微信。赔付金额5-25元不等。", category="售后政策"),
            FAQ(question="过了7天还能退货吗？", answer="超过7天无理由退货期后，如有质量问题仍可在15天内联系客服换货或维修。超过15天且在保修期内，可申请保修服务。", category="售后政策"),

            # 支付相关
            FAQ(question="支持哪些支付方式？", answer="支持：支付宝/微信支付/银联卡/Apple Pay/花呗分期（3/6/12期）/京东白条/云闪付。部分商品支持货到付款（仅限现金或POS刷卡）。", category="支付相关"),
            FAQ(question="如何申请分期付款？", answer="下单时在支付方式选择「花呗分期」或「信用卡分期」，可选3/6/12期。3期免息、6期0.6%/期、12期0.5%/期。", category="支付相关"),
            FAQ(question="支付失败怎么办？", answer="检查：银行卡余额是否充足/是否超出单笔限额/网络是否稳定。也可尝试更换支付方式或清除App缓存后重试。如仍有问题请联系客服。", category="支付相关"),
            FAQ(question="花呗分期手续费怎么算？", answer="3期免手续费、6期每期0.6%、12期每期0.5%。分期金额最低100元。", category="支付相关"),
            FAQ(question="微信支付有限额吗？", answer="微信支付单笔限额根据银行卡不同，一般为5000-50000元。大额支付建议使用银行卡快捷支付或对公转账。", category="支付相关"),

            # 会员权益
            FAQ(question="会员有什么权益？", answer="银卡98折、金卡95折、钻石9折。积分可抵扣现金（100积分=1元），生日当月双倍积分。专属客服、优先发货、免费退货等权益逐级解锁。", category="会员权益"),
            FAQ(question="如何升级会员等级？", answer="年消费满2000元升级金卡、满5000元升级钻石卡。每年1月1日根据上年消费重新评定。升级后即时生效，有效期至当年12月31日。", category="会员权益"),
            FAQ(question="积分如何获取和使用？", answer="消费1元=1积分。积分可用于：抵扣现金（100积分=1元）、兑换优惠券、兑换商品。积分有效期为获得之日起1年。", category="会员权益"),

            # 订单相关
            FAQ(question="如何取消订单？", answer="订单未发货时可在订单详情页直接取消，款项即时退回。已发货订单无法直接取消，可在收货后申请退货退款。", category="订单相关"),
            FAQ(question="发票如何开具？", answer="下单时可选择电子发票或纸质发票。电子发票在确认收货后自动发送至邮箱。纸质发票随包裹寄出。支持个人抬头和公司抬头（需提供税号）。", category="订单相关"),
            FAQ(question="可以修改订单中的商品吗？", answer="订单未发货时可以取消重下。已发货订单无法修改商品。如需增加商品建议单独下单。", category="订单相关"),

            # 账号安全
            FAQ(question="如何修改绑定的手机号？", answer="进入「账户设置」→「安全中心」→「修改手机号」，需原手机号接收验证码。如原手机号已停用，请联系客服人工核验身份后修改。", category="账号安全"),
            FAQ(question="账户被盗怎么办？", answer="立即联系客服400-888-8888冻结账户，然后修改密码、检查登录设备、开启支付密码。如已产生异常订单，客服将协助拦截和退款。", category="账号安全"),
            FAQ(question="隐私数据如何保护？", answer="通过ISO27001信息安全认证。手机号和地址在传输和存储中加密，客服系统不向AI暴露用户手机号。详见隐私政策页面。", category="账号安全"),

            # 购物指南
            FAQ(question="如何查看商品是否正品？", answer="所有商品均为品牌直供或授权经销商供货，支持专柜验货。收到商品后可扫描防伪码验证。如怀疑假货请拍照联系客服，核实后假一赔三。", category="购物指南"),
            FAQ(question="商品详情页的参数准确吗？", answer="所有参数由品牌方提供并定期更新。如收到的商品参数与页面描述不符，请拍照联系客服，将按「描述不符」处理退货退款。", category="购物指南"),
            FAQ(question="可以送礼包装吗？", answer="支持！下单时选择「礼品包装」服务（+15元），包含精美礼盒+缎带+贺卡。部分商品支持代写贺卡免费。", category="购物指南"),
            FAQ(question="有没有学生优惠？", answer="全日制在校学生凭学信网认证可享95折。在「账户设置」→「学生认证」上传学生证或学信网截图，审核通过后自动生效。", category="购物指南"),
            FAQ(question="优惠券怎么领取和使用？", answer="首页领券中心、店铺首页、会员权益页均可领取。下单时自动匹配最优优惠券。优惠券不可叠加使用（除非标注\"可叠加\"）。", category="购物指南"),

            # 其他
            FAQ(question="如何联系人工客服？", answer="在线客服时间：每天9:00-22:00。客服热线：400-888-8888。紧急问题可发邮件至service@shop.com。智能客服7×24小时在线。", category="其他"),
            FAQ(question="你们的营业时间是？", answer="在线客服每天9:00-22:00。订单系统7×24小时运行，随时可下单。仓库发货时间为工作日9:00-18:00。", category="其他"),
            FAQ(question="企业团购有优惠吗？", answer="企业团购（单笔≥50件或金额≥5000元）可享受额外折扣。请联系企业客服专线：400-888-9999 或邮件至corp@shop.com。", category="其他"),
            FAQ(question="如何成为平台的供应商/商家？", answer="请访问商家入驻页面填写申请，或发送合作意向至partner@shop.com。审核团队将在3个工作日内回复。", category="其他"),
        ]
        db.add_all(faqs)

        db.commit()
        print(f"[Seed] 完成: {len(users)}用户 {len(products)}商品 50订单 {len(faqs)}FAQ")


if __name__ == "__main__":
    reset = "--reset" in sys.argv
    if reset:
        from sqlalchemy import create_engine
        engine = create_engine(DB_URL_SYNC, echo=False)
        Base.metadata.drop_all(engine)
        print("旧数据已清除。")

    seed()
    print("[OK] 数据初始化完毕！")
