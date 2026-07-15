"""
rag.py — RAG 模块：商品知识库构建、Chroma 向量存储、检索器

知识库内容（5层）：
  1. 商品详情文档 —— 每个商品一份，含详细参数、使用场景、优缺点
  2. 品类选购指南 —— 每个品类一份，含选购要点、指标对比、避坑建议
  3. 品类保养维护 —— 每品类一份，含清洁保养、存储、寿命延长
  4. FAQ 知识 —— 25条常见问题植入向量库
  5. 售后政策详解 —— 退货/换货/退款/价保规则

- build_product_knowledge_base(): 构建 Chroma 向量索引
- get_product_retriever(): 获取检索器
- search_product_knowledge(): 搜索商品知识（供 @tool 调用）
"""

import asyncio
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from langchain_community.vectorstores import Chroma

from config import make_embeddings, CHROMA_PERSIST_DIR
from database import Product, _load_products_async, FAQ, SyncSessionFactory


# ═══════════════════════════════════════════════════════════════════════════════
# 1. 商品详情模板（按品类）
# ═══════════════════════════════════════════════════════════════════════════════
PRODUCT_TEMPLATES = {
    "手机数码": """
【{name}】— 数码产品深度解析

▎产品概述
{description}

▎详细规格
{specs_text}

▎核心卖点
- 性能体验：{name}在处理器、内存、系统优化方面的表现
- 影像能力：摄像头配置、拍照效果、视频录制能力
- 续航充电：电池容量、充电速度、日常使用续航表现
- 屏幕素质：分辨率、刷新率、色彩表现、亮度峰值
- 做工质感：机身材质、手感、重量控制、配色选择

▎适合人群
- 追求旗舰性能的重度用户
- 对拍照有专业要求的摄影爱好者
- 需要长续航的商务人士
- 注重品牌生态和用户体验的消费者

▎使用场景
- 日常通讯社交：微信、抖音、微博流畅运行
- 移动办公：邮件处理、文档编辑、视频会议
- 影音娱乐：高清视频播放、大型游戏畅玩
- 旅行记录：高质量照片和视频拍摄

▎选购对比要点
购买{name}前建议对比：
1. 与竞品的处理器性能跑分差异
2. 摄像头实拍样张对比（夜景/人像/广角）
3. 系统生态与个人使用习惯的兼容性
4. 售后服务网点的覆盖范围
5. 配件生态的丰富程度（保护壳、贴膜、充电器）

▎使用贴士
- 建议使用官方/品牌保护壳和钢化膜
- 避免长时间边充电边玩大型游戏
- 定期清理后台应用和缓存文件
- 系统更新前备份重要数据
- 避免在极端温度（低于0℃或高于40℃）下长时间使用

▎售后与保修
- 主机保修1年，充电器和数据线保修6个月
- 电池健康度低于80%可在保修期内免费更换
- 全国2000+授权维修点，支持到店和寄修
- 人为损坏（碎屏、进水）不在保修范围内
""",

    "电脑办公": """
【{name}】— 办公设备深度解析

▎产品概述
{description}

▎技术规格
{specs_text}

▎核心卖点
- 处理性能：处理器型号、核心数、多任务处理能力
- 便携性：机身重量、厚度、续航时间
- 屏幕显示：分辨率、色域覆盖、亮度、护眼认证
- 连接扩展：接口种类和数量、无线连接规格
- 安静散热：风扇噪音控制、散热效率

▎适合人群
- 需要高性能的软件工程师和数据科学家
- 注重便携的商务差旅人士
- 对屏幕色彩有要求的设计师和视频编辑
- 学生群体，需要兼顾性能和价格

▎使用场景
- 编程开发：IDE、Docker、虚拟机流畅运行
- 图形设计：Photoshop、Figma、CAD 等专业软件
- 日常办公：Office 套件、浏览器多标签、视频会议
- 内容创作：视频剪辑、音乐制作、3D 建模

▎选购建议
1. 内存至少 16GB，专业用户建议 32GB 以上
2. 硬盘优先选 SSD，容量不低于 512GB
3. 经常出差选轻薄本（<1.5kg），固定办公可选性能本
4. Mac 用户注意软件兼容性，Windows 用户关注散热和续航
5. 外设（键盘、鼠标、显示器）同样重要，预算要一并考虑

▎保养维护
- 每 3-6 个月清理一次键盘和散热孔灰尘
- 避免在柔软表面（床、沙发）上使用以防堵塞散热口
- 使用合适的电脑包/内胆包保护机身
- 电池最佳充电范围 20%-80%，避免长期满电存放
- 定期备份重要文件到云端或外置硬盘

▎售后保障
- 主机保修 2 年，电池和适配器保修 1 年
- 全国联保，部分品牌提供上门维修服务
- 意外保护计划（额外购买）：涵盖碎屏、进水等意外
""",

    "家用电器": """
【{name}】— 家用电器深度解析

▎产品概述
{description}

▎详细参数
{specs_text}

▎核心卖点
- 核心性能：电机/压缩机/加热元件等关键部件表现
- 能效等级：耗电量、节能表现、长期使用成本
- 智能功能：App控制、语音助手、智能联动
- 静音表现：运行噪音分贝值
- 清洁维护：滤网/尘盒/管道等耗材的清洗便利性

▎适合人群与场景
- 新家装修：嵌入式家电一站配齐
- 日常升级：替换老旧低效家电
- 懒人福音：扫地机器人、洗碗机解放双手
- 健康生活：净水器、空气净化器保障家居环境
- 精致烹饪：空气炸锅、蒸烤箱丰富厨房体验

▎安装须知
- 大家电（空调、热水器、净水器）建议专业人员安装
- 安装前确认：预留空间尺寸、电源插座位置、上下水条件
- 安装后测试：运行噪音、制冷/加热效果、漏水检查
- 保留安装凭证，影响后续保修

▎选购避坑指南
1. 不要只看品牌，同价位横向对比核心参数
2. 注意"赠品多"的套路——核心性能才是关键
3. 关注耗材成本（滤网、清洁剂等长期开销）
4. 确认售后覆盖范围（部分品牌三四线城市网点少）
5. 能效标识看清楚，一级能效长期省电更划算

▎安全与保养
- 定期清洁滤网/尘盒/排风口（每月检查一次）
- 大功率电器使用独立插座，避免线路过载
- 长期不用时断电并做好防尘罩
- 关注电源线老化情况，发现问题及时更换
- 使用环境温度湿度符合说明书要求

▎售后政策
- 整机保修 1-3 年（视品类），主要部件延长保修
- 安装后 7 天内发现质量问题可退换
- 24 小时售后热线 400-888-8888
- 延保服务可在购买时加购
""",

    "服饰鞋包": """
【{name}】— 服饰鞋包深度解析

▎产品概述
{description}

▎商品参数
{specs_text}

▎款式与设计
- 风格定位：商务/休闲/运动/潮流
- 搭配建议：同色系搭配显高级，亮色点缀提气色
- 季节适配：春夏轻薄透气，秋冬保暖防风
- 经典 VS 潮流：经典款不易过时，潮流款个性鲜明

▎选购指南
1. 鞋子：下午试穿（脚会略微肿胀），留一指空隙
2. 服装：看面料成分标签，纯棉透气但易皱，聚酯纤维挺括但不吸汗
3. 包包：看缝线是否均匀、拉链是否顺滑、内衬是否贴合
4. 运动鞋按运动类型选：跑步选缓震、篮球选支撑、训练选稳定
5. 网上购买注意尺码表，不同品牌尺码标准可能不同

▎面料与材质知识
- 纯棉：亲肤透气、吸汗、适合贴身衣物，但易皱缩水
- 羊毛/羊绒：保暖性好、轻盈，需干洗或手洗
- 聚酯纤维：耐磨抗皱、快干，适合运动服装
- 尼龙：轻便防水、耐磨，常用于冲锋衣和背包
- 皮革：质感高级、耐用，需定期护理上油
- GORE-TEX：防水透气，适合户外装备

▎清洗与保养
- 深浅色衣物分开洗涤，首次单独洗以防掉色
- 羊毛/羊绒衣物建议干洗，或使用专用洗涤剂手洗
- 运动鞋用软刷+中性清洁剂清洗，勿用漂白剂
- 皮鞋定期上鞋油保养，淋雨后阴干勿暴晒
- 皮包不使用时填充纸团保持形状，放入防尘袋
- 羽绒服勿干洗，选择温和机洗+低温烘干+网球拍打

▎退换说明
- 7 天无理由退货（吊牌完好、未穿着使用）
- 鞋子请在干净地面试穿，鞋底无磨损才可退
- 贴身衣物（内裤、袜子）拆封后不支持退货
- 退换货请保持原包装完整
""",

    "食品生鲜": """
【{name}】— 食品生鲜深度解析

▎产品概述
{description}

▎产品信息
{specs_text}

▎食材品质鉴别
- 外观：色泽自然、形状完整、无异常斑点
- 气味：食材本身清香/肉香，无异味、酸味
- 手感/口感：肉类有弹性、蔬果饱满、干货干燥不粘手
- 包装：真空/充氮包装更保鲜，避光包装防止氧化

▎食用方法
- 坚果干果：开袋即食，也可加入酸奶/沙拉
- 牛奶饮品：冷藏后直接饮用，或搭配咖啡/麦片
- 牛排肉类：提前冷藏解冻（勿用热水），厨房纸吸干水分后烹饪
- 海鲜水产：解冻后尽快烹饪，不宜反复冻融

▎储存保鲜知识
- 冷藏区（0-4℃）：牛奶、酸奶、新鲜蔬果、鸡蛋
- 冷冻区（-18℃）：肉类、海鲜、速冻食品
- 常温阴凉：坚果、干货、大米、调味品
- 开封后务必密封保存，坚果建议转移到密封罐
- 热带水果（香蕉、芒果）不宜放冰箱
- 生熟食品分开放置，避免交叉污染

▎食品安全提示
- 肉类内部温度达到 75℃ 以上才算全熟
- 剩菜冷藏不超过 2 天，食用前彻底加热
- 坚果如有哈喇味（油脂氧化）请勿食用
- 牛奶如出现分层、凝块、酸味表示变质
- 注意保质期 ≠ 保存期，开封后保质期会大幅缩短

▎营养与健康
- 每日坚果建议摄入 20-30g（约一小把）
- 牛奶每天 300ml 满足成人钙需求
- 红肉每周 3-4 次为宜，搭配白肉和蔬菜更均衡
- 注意食品配料表：配料越靠前含量越高

▎售后说明
- 生鲜食品不支持 7 天无理由退货
- 签收后 24 小时内发现变质/破损/错发请拍照联系客服
- 核实后全额退款或重新补发
- 运输途中轻微解冻（未完全融化）属正常现象
""",
}


# ═══════════════════════════════════════════════════════════════════════════════
# 2. 品类选购指南
# ═══════════════════════════════════════════════════════════════════════════════
CATEGORY_BUYING_GUIDES = {
    "手机数码": """
【手机数码品类选购指南】

▎如何选择适合自己的手机
1. 确定预算：2000以下中端 / 3000-5000 次旗舰 / 6000+ 旗舰
2. 看核心需求：
   - 拍照优先 → 关注传感器尺寸、长焦、夜景、人像模式
   - 游戏优先 → 关注处理器性能、散热、高刷屏、大电池
   - 商务优先 → 关注续航、信号、系统稳定性、隐私安全
   - 综合均衡 → 选各品牌旗舰款不会错
3. 系统生态：iOS 封闭流畅，Android 开放自由，华为鸿蒙自成一体
4. 品牌售后：华为/OPPO/vivo 门店多，Apple 全球联保

▎手机屏幕参数怎么看
- 分辨率：1080P 够用，2K 更细腻（耗电更高）
- 刷新率：60Hz 基础 / 90Hz 流畅 / 120Hz 丝滑 / 144Hz 游戏专属
- 亮度：室内 400nit 够用，户外需要 800nit+，HDR 需要 1000nit+
- PWM调光：高频 PWM（>1440Hz）更护眼

▎耳机选购要点
- 入耳式被动降噪好，半入耳舒适度高
- 主动降噪看降噪深度（-35dB 以上算好）
- 蓝牙版本 5.3+ 连接更稳定
- 关注续航（单次+充电盒总量）和充电速度
- 空间音频/头部追踪是加分项

▎平板选购建议
- 主要看剧 → 屏幕素质和扬声器
- 学习记笔记 → 手写笔体验和软件生态
- 轻办公 → 键盘配件和系统多任务能力
- iPad 软件生态强，Android 平板性价比高
""",

    "电脑办公": """
【电脑办公品类选购指南】

▎笔记本选购核心指标
1. CPU：Ultra 7/9（全能）、i7/i9（性能）、M3/M4（Apple生态）
2. 内存：16GB起步够用，32GB专业创作，64GB+重度渲染/AI
3. 硬盘：512GB起步，1TB推荐，SSD必选（NVMe > SATA）
4. 屏幕：2K+分辨率、100%sRGB色域、16:10比例更适合办公
5. 接口：USB-C/Thunderbolt优先级最高，HDMI和USB-A也很实用

▎台式机 VS 笔记本
- 台式机：同价位性能更强，散热好，可升级，适合固定工位
- 笔记本：便携灵活，一体性强，适合移动办公和学生
- 折中方案：笔记本+外接显示器/键鼠 = 双倍效率

▎程序员选机指南
- Web/后端开发：16GB+内存、i7/Ultra7以上、SSD必选
- 移动开发：macOS更适合iOS开发，Android开发Windows和Mac均可
- AI/数据科学：32GB+内存、独立显卡、大容量SSD
- 游戏开发：高性能独显（RTX 4060+）、大内存

▎外设推荐
- 键盘：机械键盘选红轴或茶轴，薄膜键盘选罗技MX Keys
- 鼠标：办公选罗技MX Master，轻便选Anywhere，游戏选G系列
- 显示器：27寸4K黄金尺寸，IPS面板色彩好，VA对比度高
- 屏幕挂灯：BenQ ScreenBar减少屏幕反光和眼疲劳
""",

    "家用电器": """
【家用电器品类选购指南】

▎大家电选购原则
1. 先量尺寸，再选型号 —— 预留空间、开门方向、插座位置
2. 能效优先 —— 一级能效虽然贵几百，但几年电费就省回来了
3. 看核心参数，不看花哨功能 —— 空调看制冷量，冰箱看容积，洗衣机看洗净比
4. 安装售后很重要 —— 大品牌网点多，安装师傅经验丰富

▎清洁电器（扫地机/洗地机/吸尘器）
- 扫地机器人看三样：导航避障、吸力大小、基站功能（自清洁/集尘）
- 洗地机更适合有小孩/宠物的家庭（处理湿垃圾）
- 无线吸尘器灵活机动，适合局部清洁和车内使用
- 吸力不是越大越好——超过一定阈值意义不大，噪音和续航更重要

▎厨房电器
- 空气炸锅：容量 5L 以上适合家庭，看加热方式和温控精度
- 净水器：RO反渗透过滤最彻底，通量越大出水越快
- 洗碗机：嵌入式容量大，台上式灵活安装，看烘干方式（热风 > 余温）
- 注意耗材长期成本：净水器滤芯、洗碗机清洁块每月开支

▎空调选购
- 匹数：1匹10-15㎡，1.5匹15-22㎡，2匹22-35㎡，3匹35-50㎡
- 能效比APF越高越省电，新一级 > 一级 > 二级
- 变频比定频省电舒适，差价不大建议直接选变频
- 附加功能按需选择：自清洁、WiFi智控、除湿、新风
""",

    "服饰鞋包": """
【服饰鞋包品类选购指南】

▎运动鞋选购指南
- 跑步鞋：看缓震（Nike ZoomX、Adidas Boost、Asics GEL）
- 篮球鞋：看支撑和防侧翻，高帮保护脚踝
- 训练鞋：看稳定性和灵活性，适合健身房综合训练
- 休闲鞋：舒适度和颜值并重，百搭款更实用
- 尺码：运动鞋比皮鞋大半码，跑步鞋比日常鞋大半码到一码

▎尺码测量方法
- 脚长测量：站立在白纸上描边，量脚尖到脚跟最长距离
- 鞋码换算：中国码=(脚长cm)×2-10，如25cm脚长选40码
- 不同品牌尺码偏差：Nike偏窄、Adidas偏宽、New Balance标准
- 网购不确定时买两双不同尺码，试穿后留合适的退货另一双

▎服装选购技巧
- 看面料标签：天然纤维（棉麻丝毛）透气舒适，合成纤维（涤纶尼龙）耐磨
- 看做工细节：缝线均匀、纽扣牢固、拉链顺滑、内衬平整
- 通勤穿搭：深色西装/衬衫百搭不出错，配亮色配饰点缀
- 休闲穿搭：基础款纯色T恤+牛仔裤+小白鞋永远不过时

▎箱包选购
- 登机箱：20寸/40L以下，注意各航空公司尺寸限制
- 托运箱：24-28寸，PC材质轻便耐用，铝框更坚固但更重
- 通勤包：容量 15-25L，必配笔记本电脑隔层
- 托特包：开口大容量大，适合妈妈包或购物包
""",

    "食品生鲜": """
【食品生鲜品类选购指南】

▎坚果选购
- 看外观：颗粒饱满、色泽自然、无虫蛀霉斑
- 闻气味：坚果清香无异味，哈喇味 = 变质勿买
- 看配料表：原味坚果配料只有坚果本身，调味款留意盐糖添加量
- 优选独立小包装，防潮更方便控制食用量

▎乳制品选购
- 纯牛奶蛋白质 ≥ 2.9g/100ml，越高品质越好（特仑苏 3.6g）
- 酸奶看"生牛乳"是否排第一位，益生菌数量和种类
- 巴氏杀菌奶需冷藏且保质期短，UHT常温奶保质期长
- 注意区分"乳饮料"和"纯牛奶"——乳饮料蛋白质很低

▎肉类/海鲜选购
- 看色泽：牛肉鲜红、猪肉粉红、鸡肉淡粉、海鲜色泽鲜亮
- 按压测试：新鲜肉有弹性，按压后迅速回弹
- 冷冻产品看冰晶：过多冰晶说明反复冻融，品质下降
- 原切牛排 > 调理牛排 > 合成牛排（看配料表判断）

▎大米选购
- 看品种：稻花香2号（香糯）、泰国香米（粒长）、日本越光（Q弹）
- 看产地：东北黑土地核心产区品质更好
- 看日期：新米比陈米好吃太多，生产日期越近越好
- 储存：密封防潮防虫，放几瓣大蒜或花椒可驱虫
""",
}


# ═══════════════════════════════════════════════════════════════════════════════
# 3. 通用售后政策详解
# ═══════════════════════════════════════════════════════════════════════════════
AFTERSALE_POLICY_DOC = """
【电商平台售后服务政策详解】

▎退货政策（7天无理由）
适用条件：商品完好不影响二次销售，吊牌/包装/配件完整
不适用范围：生鲜食品、个人护理、内衣物、定制商品、虚拟商品、已拆封软件
运费规则：无理由退货买家承担寄回运费，质量问题平台承担双向运费

▎换货政策（15天质量问题）
适用条件：收到商品15天内出现非人为质量问题
换货流程：提交申请 → 客服审核（1-2工作日）→ 寄回商品 → 仓库验货 → 发新货
换货运费由平台承担

▎退款时效
- 支付宝/微信支付：通过后即时到账
- 银行卡/借记卡：1-3个工作日
- 信用卡：3-7个工作日（视发卡行处理速度）
- 退款按原支付方式返还，不可改为其他方式

▎价格保护
- 降价后7天内可申请价保（秒杀/拼团/限时抢购除外）
- 申请方式：联系客服提供订单号和降价截图
- 差价原路返还，审核完成后1-3个工作日到账

▎质量投诉
- 签收后发现质量问题，请24小时内拍照取证联系客服
- 处理方式：换新 / 退货退款 / 部分退款补偿
- 重大质量问题可要求三倍赔偿（依据消费者权益保护法）
- 争议处理：平台介入 → 协商不成可投诉12315

▎发票政策
- 电子发票：确认收货后发送至邮箱，用于报销和保修凭证
- 纸质发票：随包裹寄出，请妥善保管
- 支持个人和公司抬头（公司需提供完整税号）
- 发票内容默认按商品明细开具
"""


# ═══════════════════════════════════════════════════════════════════════════════
# 文档构建函数
# ═══════════════════════════════════════════════════════════════════════════════
def _build_documents(products: list) -> list[Document]:
    """构建多层知识文档"""
    documents = []

    # ── 第1层：商品详情文档 ──
    for p in products:
        specs = p.specs or {}
        specs_text = "\n".join(f"- {k}：{v}" for k, v in specs.items())

        template = PRODUCT_TEMPLATES.get(p.category, PRODUCT_TEMPLATES["手机数码"])
        content = template.format(
            name=p.name,
            description=p.description,
            specs_text=specs_text or "暂无详细参数",
        )

        documents.append(Document(
            page_content=content,
            metadata={
                "product_id": p.id,
                "product_name": p.name,
                "category": p.category,
                "price": p.price,
                "stock": p.stock,
                "doc_type": "product_detail",
            },
        ))

    # ── 第2层：品类选购指南 ──
    for category, guide in CATEGORY_BUYING_GUIDES.items():
        documents.append(Document(
            page_content=guide,
            metadata={
                "category": category,
                "doc_type": "buying_guide",
            },
        ))

    # ── 第3层：通用售后政策 ──
    documents.append(Document(
        page_content=AFTERSALE_POLICY_DOC,
        metadata={"doc_type": "policy"},
    ))

    # ── 第4层：FAQ 知识 ──
    with SyncSessionFactory() as db:
        from sqlalchemy import select
        faqs = db.execute(select(FAQ)).scalars().all()
        for f in faqs:
            documents.append(Document(
                page_content=f"【FAQ - {f.category}】\n问：{f.question}\n答：{f.answer}",
                metadata={"doc_type": "faq", "category": f.category},
            ))

    return documents


# ═══════════════════════════════════════════════════════════════════════════════
# Chroma 构建与检索
# ═══════════════════════════════════════════════════════════════════════════════
def build_product_knowledge_base(force: bool = False) -> Chroma:
    persist_path = Path(CHROMA_PERSIST_DIR)

    if persist_path.exists() and not force and any(persist_path.iterdir()):
        print(f"Chroma 索引已存在：{CHROMA_PERSIST_DIR}")
        return Chroma(
            persist_directory=CHROMA_PERSIST_DIR,
            embedding_function=make_embeddings(),
        )

    print("正在构建商品知识库...")

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None:
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as ex:
            products = ex.submit(lambda: asyncio.run(_load_products_async())).result()
    else:
        products = asyncio.run(_load_products_async())
    print(f"  [1/3] 加载 {len(products)} 个商品")

    documents = _build_documents(products)
    print(f"  [2/3] 生成 {len(documents)} 篇知识文档（商品{len(products)} + 品类指南{len(CATEGORY_BUYING_GUIDES)} + 政策 + FAQ）")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=80,
        separators=["\n\n", "\n", "。", "，", " ", ""],
    )
    chunks = splitter.split_documents(documents)
    print(f"  [3/3] 切分为 {len(chunks)} 个文本块，正在构建向量索引...")

    embeddings = make_embeddings()
    vectorstore = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=CHROMA_PERSIST_DIR,
    )
    print(f"Chroma 索引已保存：{CHROMA_PERSIST_DIR}")
    return vectorstore


def get_product_retriever(k: int = 4):
    persist_path = Path(CHROMA_PERSIST_DIR)
    if not persist_path.exists() or not any(persist_path.iterdir()):
        raise FileNotFoundError(
            f"Chroma 索引不存在：{CHROMA_PERSIST_DIR}\n请先运行 build_product_knowledge_base()"
        )

    embeddings = make_embeddings()
    vectorstore = Chroma(
        persist_directory=CHROMA_PERSIST_DIR,
        embedding_function=embeddings,
    )
    return vectorstore.as_retriever(search_type="similarity", search_kwargs={"k": k})


def search_product_knowledge(query: str, k: int = 4) -> str:
    retriever = get_product_retriever(k=k)
    docs = retriever.invoke(query)

    if not docs:
        return f"未找到关于「{query}」的相关商品知识。"

    lines = []
    for i, doc in enumerate(docs, 1):
        name = doc.metadata.get("product_name", "")
        category = doc.metadata.get("category", "")
        price = doc.metadata.get("price", 0)
        doc_type = doc.metadata.get("doc_type", "")
        content = doc.page_content[:350]

        type_labels = {
            "product_detail": "商品详情",
            "buying_guide": "选购指南",
            "policy": "售后政策",
            "faq": "常见问题",
        }
        type_label = type_labels.get(doc_type, doc_type)

        header = f"[{i}] " + (f"{name}（{category}，¥{price}）" if name else f"【{type_label}】{category}")
        lines.append(f"{header}\n{content}")

    return "\n\n---\n\n".join(lines)


if __name__ == "__main__":
    build_product_knowledge_base(force=True)
    print("\n测试检索：")
    for q in ["降噪耳机推荐", "怎么选跑鞋", "退货运费谁出", "牛排怎么保存"]:
        print(f"\n{'='*40}\n查询: {q}\n{'='*40}")
        result = search_product_knowledge(q)
        print(result[:400])
