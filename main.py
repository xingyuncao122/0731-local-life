"""
0731本地生活圈 — FastAPI 主应用
只服务韶山人，只做韶山事。每一个账号背后，都是你的邻居。
"""
import hashlib
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Form, Query, Depends, HTTPException, Cookie
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import Session

from database import Base, engine, get_db, init_db
from models import (
    User, Post, Comment, Like, Report, Notice, AuthDocument, Violation,
    AuthLevel, PostStatus, ReportStatus,
    SECTION_NAMES, SECTION_ICONS, SECTION_RULES,
)
from sqladmin import Admin, ModelView

# ========== 应用初始化 ==========
BASE_DIR = Path(__file__).parent

# 在线人数（默认100，后续动态计算）
online_count = 100
online_count_base = 100  # 基础在线人数

# 管理员凭证（生产环境应使用环境变量）
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD_HASH = hashlib.sha256("0731admin".encode()).hexdigest()
# 论坛币兑换比例：1000论坛币 = 2元
COINS_TO_YUAN_RATE = 1000 / 2  # 500币=1元


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    db = next(get_db())
    try:
        seed_data(db)
    finally:
        db.close()
    yield


app = FastAPI(
    title="0731本地生活圈",
    description="韶山人专属的实名认证本地生活圈",
    version="1.0.0",
    lifespan=lifespan,
)

# SQLAdmin 数据面板认证中间件
class DataPanelAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.url.path.startswith("/admin/data-panel"):
            admin_id = request.cookies.get("admin_id")
            if not admin_id:
                return RedirectResponse("/admin/login")
            db = next(get_db())
            try:
                admin = db.query(User).filter(User.id == int(admin_id), User.is_super_admin == True).first()
                if not admin:
                    return RedirectResponse("/admin/login")
            finally:
                db.close()
        return await call_next(request)

app.add_middleware(DataPanelAuthMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========== 管理后台 (SQLAdmin 自动生成 CRUD) ==========
class UserAdmin(ModelView, model=User):
    column_list = [User.id, User.phone, User.nickname, User.auth_level, User.score, User.created_at, User.is_active, User.is_frozen]
    column_searchable_list = [User.phone, User.nickname]
    column_sortable_list = [User.id, User.score, User.created_at]
    can_create = True
    can_edit = True
    can_delete = True
    name = "用户"
    name_plural = "用户管理"

class PostAdmin(ModelView, model=Post):
    column_list = [Post.id, Post.title, Post.section, Post.author, Post.status, Post.likes_count, Post.comments_count, Post.views, Post.created_at]
    column_searchable_list = [Post.title, Post.content]
    column_sortable_list = [Post.id, Post.likes_count, Post.views, Post.created_at]
    name = "帖子"
    name_plural = "内容管理"

class CommentAdmin(ModelView, model=Comment):
    column_list = [Comment.id, Comment.post_id, Comment.author, Comment.content, Comment.created_at]
    name = "评论"
    name_plural = "评论管理"

class ReportAdmin(ModelView, model=Report):
    column_list = [Report.id, Report.post_id, Report.reporter_id, Report.reason, Report.status, Report.created_at]
    name = "举报"
    name_plural = "举报处理"

class NoticeAdmin(ModelView, model=Notice):
    column_list = [Notice.id, Notice.title, Notice.is_active, Notice.created_at]
    can_create = True
    can_edit = True
    name = "公告"
    name_plural = "公告管理"

class ViolationAdmin(ModelView, model=Violation):
    column_list = [Violation.id, Violation.user_id, Violation.violation_type, Violation.reason, Violation.created_at]
    name = "违规"
    name_plural = "违规记录"

class AuthDocumentAdmin(ModelView, model=AuthDocument):
    column_list = [AuthDocument.id, AuthDocument.user_id, AuthDocument.doc_type, AuthDocument.status, AuthDocument.uploaded_at]
    name = "认证"
    name_plural = "认证审核"

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# 全局上下文
def template_context(request: Request, **extra):
    """构建模板通用上下文"""
    user_id = request.cookies.get("user_id")
    user = None
    if user_id:
        db = next(get_db())
        user = db.query(User).filter(User.id == int(user_id)).first()
        db.close()

    return {
        "request": request,
        "user": user,
        "auth_levels": AuthLevel,
        "section_names": SECTION_NAMES,
        "section_icons": SECTION_ICONS,
        "section_rules": SECTION_RULES,
        "all_sections": [
            {"id": k, "name": v, "icon": SECTION_ICONS.get(k, "📝")}
            for k, v in SECTION_NAMES.items()
        ],
        **extra,
    }


# ========== 辅助函数 ==========
def hash_id_number(id_num: str) -> str:
    return hashlib.sha256(f"0731_salt_{id_num}".encode()).hexdigest()

def get_or_create_user(db: Session, phone: str = None, nickname: str = "韶山新邻居") -> User:
    """获取或创建模拟用户 (MVP简化: 不强制真实认证)"""
    if phone:
        user = db.query(User).filter(User.phone == phone).first()
        if user:
            return user
    user = User(
        phone=phone or "13800000000",
        id_number_hash=hash_id_number("430382199001011234"),
        nickname=nickname,
        auth_level=AuthLevel.standard,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

def format_relative_time(dt: datetime) -> str:
    if not dt:
        return ""
    now = datetime.now()
    diff = now - dt
    if diff < timedelta(minutes=1): return "刚刚"
    if diff < timedelta(hours=1): return f"{diff.seconds // 60}分钟前"
    if diff < timedelta(days=1): return f"{diff.seconds // 3600}小时前"
    if diff < timedelta(days=7): return f"{diff.days}天前"
    return dt.strftime("%m月%d日")

# 注册模板全局函数
templates.env.globals.update(
    format_time=format_relative_time,
    SECTION_NAMES=SECTION_NAMES,
    SECTION_ICONS=SECTION_ICONS,
    SECTION_RULES=SECTION_RULES,
    AuthLevel=AuthLevel,
)


def seed_data(db: Session):
    """初始化演示数据"""
    # 确保超级管理员始终存在
    admin = db.query(User).filter(User.is_super_admin == True).first()
    if not admin:
        admin = User(phone="13800000000", id_number_hash=hash_id_number("admin"),
                     nickname="超级管理员", auth_level=AuthLevel.business,
                     is_super_admin=True, score=9999)
        db.add(admin)
        db.commit()

    if db.query(User).count() > 1:
        return  # 已有用户数据，跳过演示数据

    # 创建用户
    users = [
        User(phone="13873210001", id_number_hash=hash_id_number("430382199001010001"),
             nickname="韶山老食客", auth_level=AuthLevel.standard, score=120),
        User(phone="13873210002", id_number_hash=hash_id_number("430382199001010002"),
             nickname="韶山小帮手", auth_level=AuthLevel.advanced, score=200),
        User(phone="13873210003", id_number_hash=hash_id_number("430382199001010003"),
             nickname="清溪镇老李", auth_level=AuthLevel.standard, score=80),
        User(phone="13873210004", id_number_hash=hash_id_number("430382199001010004"),
             nickname="韶山通勤小王", auth_level=AuthLevel.advanced, score=150),
        User(phone="13873210005", id_number_hash=hash_id_number("430382199001010005"),
             nickname="韶山安防科技", auth_level=AuthLevel.business, score=300),
        User(phone="13873210006", id_number_hash=hash_id_number("430382199001010006"),
             nickname="韶山百事通", auth_level=AuthLevel.advanced, score=180),
        User(phone="13873210007", id_number_hash=hash_id_number("430382199001010007"),
             nickname="韶山妈妈帮", auth_level=AuthLevel.standard, score=90),
        User(phone="13873210008", id_number_hash=hash_id_number("430382199001010008"),
             nickname="韶山好市民", auth_level=AuthLevel.advanced, score=250),
        User(phone="13873210009", id_number_hash=hash_id_number("430382199001010009"),
             nickname="韶山记忆", auth_level=AuthLevel.standard, score=110),
        User(phone="13873210010", id_number_hash=hash_id_number("430382199001010010"),
             nickname="明珠小区小张", auth_level=AuthLevel.standard, score=60),
    ]
    for u in users:
        db.add(u)
    db.flush()

    # 创建帖子
    now = datetime.now()
    posts = [
        Post(user_id=users[0].id, section="chifan",
             title="【测评】韶山这家新开的米粉店太绝了！汤底熬足8小时",
             content='<p>作为一个在韶山吃了30年米粉的老食客，今天必须安利这家新店！</p><p><strong>📍位置：</strong>清溪镇人民路128号，韶山宾馆斜对面</p><p><strong>🍜 招牌：</strong>红烧牛肉粉，汤底用牛骨+鸡架+20多种香料熬足8小时，鲜香浓郁。</p><p><strong>💰 人均：</strong>15-25元，分量很足</p><p><strong>⭐ 评分：</strong>4.5/5</p><p><em>以上为个人真实消费体验，非商业推广</em></p>',
             likes_count=128, comments_count=46, views=2341,
             created_at=now - timedelta(hours=3)),
        Post(user_id=users[1].id, section="bianmin",
             title="【推荐】韶山靠谱水电工王师傅，从业20年，价格公道",
             content='<p>家里水管漏水好几天，经邻居推荐找了王师傅，确实靠谱！</p><p><strong>🔧 服务：</strong>水电维修、管道疏通、卫浴安装、电路改造</p><p><strong>💰 价格：</strong>水管维修80-150元，疏通下水道100元起</p><p>王师傅韶山本地人，从业20多年，干活仔细不偷工减料。</p>',
             price_info="80-200元", likes_count=96, comments_count=32, views=1823,
             created_at=now - timedelta(hours=5)),
        Post(user_id=users[2].id, section="jishi",
             title="【转让】九成新海尔冰箱，300元自提，清溪镇自取",
             content='<p>家里换大冰箱，这台小的转让。海尔三门冰箱，用了不到一年，九成新。</p><p><strong>💰 价格：</strong>300元，不议价</p><p><strong>📍 地址：</strong>清溪镇韶山北路自取</p>',
             price_info="300元", likes_count=35, comments_count=18, views=892,
             created_at=now - timedelta(hours=8)),
        Post(user_id=users[3].id, section="chuxing",
             title="【拼车】明天早上8点韶山到长沙，有3个空位，20元/人",
             content='<p>明天(15号)早上8点从韶山出发去长沙，五座轿车，还有3个空位。</p><p><strong>💰 费用：</strong>20元/人</p><p><strong>📍 上车点：</strong>韶山市政府门口</p><p><strong>⚠️ 需双方实名互认后成行</strong></p>',
             price_info="20元/人", likes_count=22, comments_count=15, views=456,
             created_at=now - timedelta(hours=2)),
        Post(user_id=users[4].id, section="shuma",
             title="【服务】专业监控安装+网络布线，韶山本地10年经验，质保2年",
             content='<p>韶山本地团队，10年安防监控经验，服务韶山各大小区和商户。</p><p><strong>📹 监控：</strong>家用/商用监控方案设计、安装、维护</p><p><strong>🌐 网络：</strong>WiFi覆盖优化、综合布线、企业组网</p><p><strong>💰 报价：</strong>免费上门勘测出方案</p>',
             price_info="面议", likes_count=67, comments_count=23, views=1234,
             created_at=now - timedelta(days=1)),
        Post(user_id=users[5].id, section="xinxiangshi",
             title="【通知】清溪镇明天上午8:00-18:00停水通知",
             content='<p>接韶山市自来水公司通知，因管道维修，清溪镇以下区域明天停水：</p><p>人民路、韶山路、英雄路沿线</p><p><strong>⏰ 时间：</strong>6月15日 8:00-18:00</p><p>请相关区域居民提前做好储水准备。</p>',
             views=980, likes_count=15, comments_count=8,
             created_at=now - timedelta(hours=1)),
        Post(user_id=users[6].id, section="jiaoyu",
             title="【分享】韶山实验小学和韶山学校小学部怎么选？真实对比",
             content='<p>两个学校都考察过，分享下真实体验供家长参考：</p><p><strong>🏫 韶山实验小学：</strong>新建校区，硬件好，班额小(35人)</p><p><strong>🏫 韶山学校小学部：</strong>老牌名校，师资稳定，课外活动丰富</p><p>两所学校教学质量都不错，关键是看孩子性格和离家距离。</p>',
             likes_count=203, comments_count=89, views=5678,
             created_at=now - timedelta(days=2)),
        Post(user_id=users[8].id, section="chaguan",
             title="【怀旧】晒一张1990年代的韶山火车站老照片",
             content='<p>整理老相册翻出来的，1990年代的韶山火车站。那时候站前广场还是水泥地，周围都是农田。现在变化太大了！</p><p>各位老韶山人来认认，还记得这个场景吗？</p>',
             likes_count=356, comments_count=128, views=8900,
             created_at=now - timedelta(days=3)),
        Post(user_id=users[7].id, section="jianyan",
             title="【建议】清溪镇人民路与韶山路交叉口建议增加红绿灯",
             content='<p>这个路口车流量大，特别是早晚高峰，经常堵车且存在安全隐患。</p><p>建议交通部门在此增设红绿灯或至少设置减速带。</p><p><strong>📸 附图：</strong>路口实拍照片（高峰期车流情况）</p>',
             likes_count=489, comments_count=156, views=12300,
             created_at=now - timedelta(days=5)),
        Post(user_id=users[9].id, section="xiaoqu",
             title="【寻宠】清溪明珠小区走失一只黄色泰迪，戴红色项圈",
             content='<p>6月13日下午在清溪明珠小区附近走失，黄色泰迪犬，约3公斤，戴红色皮质项圈。</p><p>如有人看到请联系我，当面酬谢！</p>',
             likes_count=42, comments_count=12, views=780,
             created_at=now - timedelta(hours=12)),
    ]
    for p in posts:
        db.add(p)
    db.flush()

    # 创建评论
    sample_comments = [
        Comment(post_id=posts[0].id, user_id=users[2].id,
                content="今天中午去吃了！确实不错，汤底很鲜，就是等了大半个小时😅",
                created_at=now - timedelta(hours=2)),
        Comment(post_id=posts[0].id, user_id=users[5].id,
                content="请问早上几点开门？想明天去吃早餐",
                created_at=now - timedelta(hours=4)),
        Comment(post_id=posts[0].id, user_id=users[0].id,
                content="回复：早上6点半就开门了，早餐有米粉和馄饨",
                created_at=now - timedelta(hours=3)),
        Comment(post_id=posts[1].id, user_id=users[2].id,
                content="已收藏！家里正好有个开关要换", created_at=now - timedelta(hours=1)),
        Comment(post_id=posts[6].id, user_id=users[0].id,
                content="我家在实小读，老师很负责，推荐！", created_at=now - timedelta(days=1)),
        Comment(post_id=posts[6].id, user_id=users[7].id,
                content="韶山学校的课外活动确实多，孩子很喜欢", created_at=now - timedelta(days=1)),
        Comment(post_id=posts[8].id, user_id=users[5].id,
                content="满满的回忆！那时候每周都去火车站看火车", created_at=now - timedelta(days=2)),
        Comment(post_id=posts[8].id, user_id=users[7].id,
                content="我也有这张照片！改天也翻出来晒晒", created_at=now - timedelta(days=2)),
        Comment(post_id=posts[7].id, user_id=users[1].id,
                content="支持！每次过这个路口都提心吊胆", created_at=now - timedelta(days=4)),
    ]
    for c in sample_comments:
        db.add(c)

    # 社区公告
    notices = [
        Notice(title="【系统通知】平台全新升级！新增数码科技板块",
               content="涵盖电脑维修、监控安装、音响调试、网络布线等服务，欢迎相关从业者入驻。"),
        Notice(title="【社区活动】韶山美食打卡活动火热进行中",
               content="发帖分享你最爱的本地美食，带上3张实拍图，赢取社区好礼！"),
        Notice(title="【安全提醒】请勿轻信未认证用户发布的交易信息",
               content="涉及钱财务必当面交易，核实对方身份。发现可疑信息请及时举报。"),
        Notice(title="【认证提示】完成标准认证即可发帖互动",
               content="标准认证需要手机号+身份证号+人脸识别，完成即可解锁发帖评论功能。"),
    ]
    for n in notices:
        db.add(n)

    db.commit()


# ========== 页面路由 ==========

@app.get("/", response_class=HTMLResponse)
def page_index(request: Request, db: Session = Depends(get_db)):
    """首页"""
    notices = db.query(Notice).filter(Notice.is_active == True).order_by(Notice.created_at.desc()).limit(5).all()
    hot_posts = db.query(Post).filter(Post.status == PostStatus.published)\
        .order_by(Post.likes_count.desc()).limit(8).all()
    # 置顶帖子
    pinned_posts = db.query(Post).filter(
        Post.status == PostStatus.published,
        Post.is_pinned == True,
    ).order_by(Post.pinned_at.desc()).all()
    # 各板块帖子数
    section_counts = {}
    for sid in SECTION_NAMES:
        section_counts[sid] = db.query(Post).filter(Post.section == sid, Post.status == PostStatus.published).count()
    total_users = db.query(User).count()
    total_posts = db.query(Post).filter(Post.status == PostStatus.published).count()

    return templates.TemplateResponse("index.html", template_context(request,
        notices=notices, hot_posts=hot_posts, pinned_posts=pinned_posts,
        section_counts=section_counts,
        total_users=total_users, total_posts=total_posts,
    ))


@app.get("/section/{section_id}", response_class=HTMLResponse)
def page_section(request: Request, section_id: str,
                 sort: str = Query("latest"),
                 db: Session = Depends(get_db)):
    """板块列表页"""
    if section_id not in SECTION_NAMES:
        raise HTTPException(404, "板块不存在")

    query = db.query(Post).filter(Post.section == section_id, Post.status == PostStatus.published)
    if sort == "hot":
        query = query.order_by(Post.likes_count.desc())
    elif sort == "comments":
        query = query.order_by(Post.comments_count.desc())
    else:
        query = query.order_by(Post.created_at.desc())

    posts = query.limit(20).all()

    return templates.TemplateResponse("section.html", template_context(request,
        section_id=section_id,
        section_name=SECTION_NAMES[section_id],
        section_icon=SECTION_ICONS[section_id],
        section_rule=SECTION_RULES.get(section_id, ""),
        posts=posts, sort=sort,
    ))


@app.get("/post/{post_id}", response_class=HTMLResponse)
def page_post(request: Request, post_id: int, db: Session = Depends(get_db)):
    """帖子详情页"""
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(404, "帖子不存在")

    post.views += 1
    db.commit()

    comments = db.query(Comment).filter(Comment.post_id == post_id)\
        .order_by(Comment.created_at.desc()).all()

    return templates.TemplateResponse("post.html", template_context(request,
        post=post, comments=comments,
    ))


@app.get("/create", response_class=HTMLResponse)
def page_create(request: Request):
    """发帖页"""
    return templates.TemplateResponse("create_post.html", template_context(request))


@app.get("/auth", response_class=HTMLResponse)
def page_auth(request: Request):
    """认证页"""
    return templates.TemplateResponse("auth.html", template_context(request))


@app.get("/profile", response_class=HTMLResponse)
def page_profile(request: Request, db: Session = Depends(get_db)):
    """个人中心"""
    user_id = request.cookies.get("user_id")
    if not user_id:
        return RedirectResponse("/auth")
    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user:
        return RedirectResponse("/auth")
    my_posts = db.query(Post).filter(Post.user_id == user.id).order_by(Post.created_at.desc()).all()
    my_comments = db.query(Comment).filter(Comment.user_id == user.id).order_by(Comment.created_at.desc()).limit(20).all()
    return templates.TemplateResponse("profile.html", template_context(request,
        profile_user=user, my_posts=my_posts, my_comments=my_comments,
    ))


@app.get("/search", response_class=HTMLResponse)
def page_search(request: Request, q: str = Query(""), section: str = Query(""),
                db: Session = Depends(get_db)):
    """搜索页"""
    posts = []
    if q:
        query = db.query(Post).filter(
            Post.status == PostStatus.published,
            (Post.title.contains(q)) | (Post.content.contains(q))
        )
        if section:
            query = query.filter(Post.section == section)
        posts = query.order_by(Post.created_at.desc()).limit(30).all()
    return templates.TemplateResponse("search.html", template_context(request,
        query=q, posts=posts, active_section=section,
    ))


@app.get("/help", response_class=HTMLResponse)
def page_help(request: Request):
    """帮助中心"""
    return templates.TemplateResponse("help.html", template_context(request))


# ========== API 路由 ==========

@app.post("/api/auth/login")
def api_login(
    phone: str = Form(...),
    db: Session = Depends(get_db),
):
    """模拟登录"""
    user = db.query(User).filter(User.phone == phone).first()
    if not user:
        user = User(
            phone=phone,
            id_number_hash=hash_id_number("430382199001019999"),
            nickname=f"韶山邻居{phone[-4:]}",
            auth_level=AuthLevel.basic,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    resp = JSONResponse({"ok": True, "user_id": user.id, "auth_level": user.auth_level.value})
    resp.set_cookie("user_id", str(user.id), max_age=86400 * 30)
    return resp


@app.post("/api/auth/upgrade")
def api_upgrade_auth(
    level: str = Form(...),
    user_id: str = Cookie(None),
    db: Session = Depends(get_db),
):
    """升级认证等级 (模拟)"""
    if not user_id:
        raise HTTPException(401)
    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user:
        raise HTTPException(404)
    try:
        user.auth_level = AuthLevel(level)
        db.commit()
        return {"ok": True, "auth_level": user.auth_level.value}
    except ValueError:
        raise HTTPException(400, "无效的认证等级")


@app.post("/api/posts")
def api_create_post(
    request: Request,
    section: str = Form(...),
    title: str = Form(...),
    content: str = Form(...),
    price_info: str = Form(""),
    contact_info: str = Form(""),
    user_id: str = Cookie(None),
    db: Session = Depends(get_db),
):
    """创建帖子"""
    if not user_id:
        raise HTTPException(401)
    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user or user.auth_level == AuthLevel.basic:
        raise HTTPException(403, "需要标准认证才能发帖")

    post = Post(
        user_id=user.id, section=section, title=title,
        content=content, price_info=price_info, contact_info=contact_info,
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    return {"ok": True, "post_id": post.id}


@app.post("/api/comments")
def api_create_comment(
    post_id: int = Form(...),
    content: str = Form(...),
    user_id: str = Cookie(None),
    db: Session = Depends(get_db),
):
    """发表评论"""
    if not user_id:
        raise HTTPException(401)
    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user or user.auth_level == AuthLevel.basic:
        raise HTTPException(403, "需要标准认证才能评论")

    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(404)

    comment = Comment(post_id=post_id, user_id=user.id, content=content)
    post.comments_count += 1
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return {"ok": True, "comment_id": comment.id}


@app.post("/api/likes")
def api_toggle_like(
    post_id: int = Form(...),
    user_id: str = Cookie(None),
    db: Session = Depends(get_db),
):
    """切换点赞"""
    if not user_id:
        raise HTTPException(401)
    uid = int(user_id)
    existing = db.query(Like).filter(Like.post_id == post_id, Like.user_id == uid).first()
    post = db.query(Post).filter(Post.id == post_id).first()
    if existing:
        db.delete(existing)
        post.likes_count = max(0, post.likes_count - 1)
        db.commit()
        return {"ok": True, "liked": False, "count": post.likes_count}
    else:
        like = Like(post_id=post_id, user_id=uid)
        post.likes_count += 1
        db.add(like)
        db.commit()
        return {"ok": True, "liked": True, "count": post.likes_count}


@app.post("/api/reports")
def api_report(
    post_id: int = Form(...),
    reason: str = Form(...),
    user_id: str = Cookie(None),
    db: Session = Depends(get_db),
):
    """举报帖子"""
    if not user_id:
        raise HTTPException(401)
    report = Report(post_id=post_id, reporter_id=int(user_id), reason=reason)
    db.add(report)
    db.commit()
    return {"ok": True}


# ========== 超级管理员 API ==========
def check_super_admin(db: Session, user_id: str = None, admin_id: str = None) -> User:
    """验证超级管理员身份（兼容user_id和admin_id两种cookie）"""
    uid = admin_id or user_id
    if not uid:
        raise HTTPException(401, "请先登录")
    user = db.query(User).filter(User.id == int(uid), User.is_super_admin == True).first()
    if not user:
        raise HTTPException(403, "需要超级管理员权限")
    return user


@app.post("/api/admin/delete_post")
def api_admin_delete_post(
    post_id: int = Form(...),
    user_id: str = Cookie(None),
    admin_id: str = Cookie(None),
    db: Session = Depends(get_db),
):
    """超级管理员删除任意帖子"""
    super_admin = check_super_admin(db, user_id=user_id, admin_id=admin_id)
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(404, "帖子不存在")
    # 删除关联的评论、点赞、举报
    db.query(Comment).filter(Comment.post_id == post_id).delete()
    db.query(Like).filter(Like.post_id == post_id).delete()
    db.query(Report).filter(Report.post_id == post_id).delete()
    db.delete(post)
    db.commit()
    return {"ok": True, "msg": f"帖子 #{post_id} 已删除"}


@app.post("/api/admin/ban_user")
def api_admin_ban_user(
    target_user_id: int = Form(...),
    reason: str = Form("违规处理"),
    user_id: str = Cookie(None),
    admin_id: str = Cookie(None),
    db: Session = Depends(get_db),
):
    """超级管理员封禁用户"""
    super_admin = check_super_admin(db, user_id=user_id, admin_id=admin_id)
    target = db.query(User).filter(User.id == target_user_id).first()
    if not target:
        raise HTTPException(404, "用户不存在")
    target.is_frozen = True
    # 记录违规
    v = Violation(user_id=target_user_id, violation_type="ban", reason=reason)
    db.add(v)
    db.commit()
    return {"ok": True, "msg": f"用户 {target.nickname}（#{target_user_id}）已被封禁"}


@app.post("/api/admin/unban_user")
def api_admin_unban_user(
    target_user_id: int = Form(...),
    user_id: str = Cookie(None),
    admin_id: str = Cookie(None),
    db: Session = Depends(get_db),
):
    """超级管理员解封用户"""
    check_super_admin(db, user_id=user_id, admin_id=admin_id)
    target = db.query(User).filter(User.id == target_user_id).first()
    if not target:
        raise HTTPException(404, "用户不存在")
    target.is_frozen = False
    db.commit()
    return {"ok": True, "msg": f"用户 {target.nickname}（#{target_user_id}）已解封"}


# ========== 管理后台 API ==========

@app.post("/api/admin/login")
def api_admin_login(
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    """管理员登录 - 账号:admin 密码:0731admin"""
    pwd_hash = hashlib.sha256(password.encode()).hexdigest()
    if username != ADMIN_USERNAME or pwd_hash != ADMIN_PASSWORD_HASH:
        raise HTTPException(401, "账号或密码错误")
    # 查找或创建管理员用户
    admin_user = db.query(User).filter(User.is_super_admin == True).first()
    if not admin_user:
        admin_user = User(
            phone="13800000000",
            id_number_hash=hash_id_number("admin"),
            nickname="超级管理员",
            auth_level=AuthLevel.business,
            is_super_admin=True,
            score=9999,
            forum_coins=99999,
        )
        db.add(admin_user)
        db.commit()
        db.refresh(admin_user)
    resp = JSONResponse({"ok": True, "user_id": admin_user.id, "nickname": admin_user.nickname})
    resp.set_cookie("admin_id", str(admin_user.id), max_age=86400)
    return resp


@app.post("/api/admin/logout")
def api_admin_logout():
    """管理员退出"""
    resp = JSONResponse({"ok": True})
    resp.delete_cookie("admin_id")
    return resp


def check_admin(request: Request, db: Session) -> User:
    """验证管理员身份"""
    admin_id = request.cookies.get("admin_id")
    if not admin_id:
        raise HTTPException(401, "请先登录管理后台")
    admin = db.query(User).filter(User.id == int(admin_id), User.is_super_admin == True).first()
    if not admin:
        raise HTTPException(403, "需要管理员权限")
    return admin


@app.get("/api/admin/stats")
def api_admin_stats(
    request: Request,
    db: Session = Depends(get_db),
):
    """管理后台统计数据"""
    check_admin(request, db)
    total_users = db.query(User).count()
    total_posts = db.query(Post).count()
    total_comments = db.query(Comment).count()
    total_reports = db.query(Report).filter(Report.status == ReportStatus.pending).count()
    today_users = db.query(User).filter(
        User.created_at >= datetime.now().replace(hour=0, minute=0, second=0)
    ).count()
    return {
        "total_users": total_users,
        "total_posts": total_posts,
        "total_comments": total_comments,
        "pending_reports": total_reports,
        "today_users": today_users,
        "online_count": online_count,
    }


# ========== 签到系统 ==========

@app.post("/api/checkin")
def api_checkin(
    user_id: str = Cookie(None),
    db: Session = Depends(get_db),
):
    """每日签到，随机获得1-10论坛币"""
    if not user_id:
        raise HTTPException(401, "请先登录")
    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user:
        raise HTTPException(404, "用户不存在")

    today = datetime.now().strftime("%Y-%m-%d")
    if user.last_check_in_date == today:
        raise HTTPException(400, "今天已经签到过了，明天再来吧！")

    import random
    coins = random.randint(1, 10)
    user.forum_coins = (user.forum_coins or 0) + coins
    user.last_check_in_date = today
    db.commit()

    return {
        "ok": True,
        "coins_earned": coins,
        "total_coins": user.forum_coins,
        "yuan_value": round(user.forum_coins / COINS_TO_YUAN_RATE, 2),
    }


@app.get("/api/checkin/status")
def api_checkin_status(
    user_id: str = Cookie(None),
    db: Session = Depends(get_db),
):
    """查询签到状态"""
    if not user_id:
        return {"checked_in": True, "total_coins": 0}
    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user:
        return {"checked_in": True, "total_coins": 0}
    today = datetime.now().strftime("%Y-%m-%d")
    return {
        "checked_in": user.last_check_in_date == today,
        "total_coins": user.forum_coins or 0,
        "yuan_value": round((user.forum_coins or 0) / COINS_TO_YUAN_RATE, 2),
    }


# ========== 帖子置顶管理 ==========

@app.post("/api/admin/pin_post")
def api_admin_pin_post(
    post_id: int = Form(...),
    days: int = Form(30),  # 默认30天
    request: Request = None,
    db: Session = Depends(get_db),
):
    """管理员置顶帖子（5元/月 = 2500论坛币/月）"""
    from fastapi import Request as Req
    admin = check_admin(request, db)
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(404, "帖子不存在")

    post.is_pinned = True
    post.pinned_at = datetime.now()
    post.pinned_expires_at = datetime.now() + timedelta(days=days)
    db.commit()

    return {
        "ok": True,
        "msg": f"帖子「{post.title[:20]}」已置顶{days}天",
        "expires_at": post.pinned_expires_at.strftime("%Y-%m-%d %H:%M"),
    }


@app.post("/api/admin/unpin_post")
def api_admin_unpin_post(
    post_id: int = Form(...),
    request: Request = None,
    db: Session = Depends(get_db),
):
    """取消置顶"""
    admin = check_admin(request, db)
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(404, "帖子不存在")
    post.is_pinned = False
    post.pinned_at = None
    post.pinned_expires_at = None
    db.commit()
    return {"ok": True, "msg": f"帖子「{post.title[:20]}」已取消置顶"}


# ========== 帖子标签管理 ==========

@app.post("/api/admin/toggle_tag")
def api_admin_toggle_tag(
    post_id: int = Form(...),
    tag: str = Form(...),  # "hot" 或 "essential"
    request: Request = None,
    db: Session = Depends(get_db),
):
    """切换帖子标签（火热/加精）"""
    admin = check_admin(request, db)
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(404, "帖子不存在")

    tag_names = {"hot": "火热", "essential": "加精"}
    if tag == "hot":
        post.is_hot = not post.is_hot
        status = post.is_hot
    elif tag == "essential":
        post.is_essential = not post.is_essential
        status = post.is_essential
    else:
        raise HTTPException(400, "无效标签")

    db.commit()
    return {
        "ok": True,
        "tag": tag,
        "enabled": status,
        "msg": f"已{'设置' if status else '取消'}「{tag_names.get(tag, tag)}」",
    }


@app.post("/api/admin/batch_tag")
def api_admin_batch_tag(
    post_id: int = Form(...),
    is_hot: bool = Form(False),
    is_essential: bool = Form(False),
    is_pinned: bool = Form(False),
    request: Request = None,
    db: Session = Depends(get_db),
):
    """批量设置帖子所有标签"""
    admin = check_admin(request, db)
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(404, "帖子不存在")
    post.is_hot = is_hot
    post.is_essential = is_essential
    if is_pinned and not post.is_pinned:
        post.is_pinned = True
        post.pinned_at = datetime.now()
        post.pinned_expires_at = datetime.now() + timedelta(days=30)
    elif not is_pinned:
        post.is_pinned = False
        post.pinned_at = None
        post.pinned_expires_at = None
    db.commit()
    return {"ok": True, "msg": f"帖子标签已更新"}


# ========== 在线人数 API ==========

@app.get("/api/online_count")
def api_online_count():
    """获取当前在线人数"""
    return {"count": online_count}


@app.post("/api/admin/update_online_count")
def api_admin_update_online(
    count: int = Form(...),
    request: Request = None,
    db: Session = Depends(get_db),
):
    """管理员更新在线人数"""
    global online_count
    check_admin(request, db)
    online_count = max(0, count)
    return {"ok": True, "count": online_count}


# ========== 论坛币兑换 ==========

@app.post("/api/coins/exchange")
def api_coins_exchange(
    coins: int = Form(...),
    user_id: str = Cookie(None),
    db: Session = Depends(get_db),
):
    """论坛币兑换（1000币=2元）"""
    if not user_id:
        raise HTTPException(401)
    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user:
        raise HTTPException(404)
    if coins < 1000:
        raise HTTPException(400, "最低兑换1000论坛币")
    if (user.forum_coins or 0) < coins:
        raise HTTPException(400, f"论坛币不足，当前余额：{user.forum_coins}币")

    yuan = coins / COINS_TO_YUAN_RATE
    user.forum_coins -= coins
    db.commit()
    return {
        "ok": True,
        "coins_used": coins,
        "yuan_value": round(yuan, 2),
        "remaining_coins": user.forum_coins,
        "msg": f"已使用{coins}论坛币，抵扣{round(yuan, 2)}元",
    }


# ========== 自动检测热门帖子 ==========

def update_hot_posts(db: Session):
    """自动更新热门帖子：浏览量>500 或 点赞>50 自动标记为火热"""
    threshold_date = datetime.now() - timedelta(days=7)
    hot_posts = db.query(Post).filter(
        Post.status == PostStatus.published,
        Post.created_at >= threshold_date,
        ((Post.views >= 500) | (Post.likes_count >= 50)),
        Post.is_hot == False,
    ).all()
    for p in hot_posts:
        p.is_hot = True
    if hot_posts:
        db.commit()


# ========== 管理后台页面路由 ==========

# 管理员登录页面
@app.get("/admin/login", response_class=HTMLResponse)
def page_admin_login(request: Request):
    """管理员登录页面"""
    return templates.TemplateResponse("admin_login.html", template_context(request))


# 管理后台仪表盘
@app.get("/admin/dashboard", response_class=HTMLResponse)
def page_admin_dashboard(request: Request, db: Session = Depends(get_db)):
    """管理后台仪表盘"""
    admin_id = request.cookies.get("admin_id")
    if not admin_id:
        return RedirectResponse("/admin/login")
    admin_user = db.query(User).filter(User.id == int(admin_id), User.is_super_admin == True).first()
    if not admin_user:
        return RedirectResponse("/admin/login")

    # 统计数据
    total_users = db.query(User).count()
    total_posts = db.query(Post).count()
    total_comments = db.query(Comment).count()
    pending_reports = db.query(Report).filter(Report.status == ReportStatus.pending).count()
    today = datetime.now().replace(hour=0, minute=0, second=0)
    today_users = db.query(User).filter(User.created_at >= today).count()

    # 所有帖子（管理用）
    all_posts = db.query(Post).order_by(Post.created_at.desc()).limit(100).all()
    # 所有用户
    all_users = db.query(User).order_by(User.id.desc()).limit(50).all()
    # 待处理举报
    reports = db.query(Report).filter(Report.status == ReportStatus.pending).order_by(Report.created_at.desc()).limit(20).all()

    # 更新热门
    update_hot_posts(db)

    return templates.TemplateResponse("admin_dashboard.html", template_context(request,
        admin_user=admin_user,
        total_users=total_users,
        total_posts=total_posts,
        total_comments=total_comments,
        pending_reports=pending_reports,
        today_users=today_users,
        online_count=online_count,
        all_posts=all_posts,
        all_users=all_users,
        reports=reports,
    ))


# 管理后台首页 - 重定向到仪表盘
@app.get("/admin", response_class=HTMLResponse)
def page_admin_index(request: Request):
    admin_id = request.cookies.get("admin_id")
    if admin_id:
        return RedirectResponse("/admin/dashboard")
    return RedirectResponse("/admin/login")


# ========== SQLAdmin 数据管理 (放在最后注册，避免拦截自定义路由) ==========
admin = Admin(
    app=app,
    engine=engine,
    title="0731本地生活圈 - 数据管理",
    base_url="/admin/data-panel",
)

for view in [UserAdmin, PostAdmin, CommentAdmin, ReportAdmin, NoticeAdmin, ViolationAdmin, AuthDocumentAdmin]:
    admin.add_view(view)

# 重定向：从 /admin/data 到 SQLAdmin
@app.get("/admin/data", response_class=HTMLResponse)
def page_admin_data(request: Request):
    """SQLAdmin数据管理入口"""
    admin_id = request.cookies.get("admin_id")
    if not admin_id:
        return RedirectResponse("/admin/login")
    return RedirectResponse("/admin/data-panel/user/list")


# ========== 启动入口 ==========
if __name__ == "__main__":
    import uvicorn
    print("\n" + "="*60)
    print("   0731本地生活圈")
    print("   只服务韶山人，只做韶山事")
    print("   每一个账号背后，都是你的邻居")
    print("="*60)
    print(f"   访问地址: http://127.0.0.1:8000")
    print(f"   API 文档: http://127.0.0.1:8000/docs")
    print("="*60 + "\n")
    uvicorn.run(app, host="127.0.0.1", port=8000)
