"""数据模型 — 对应PRD中所有功能模块"""
import enum
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Enum, ForeignKey, Boolean, Float
)
from sqlalchemy.orm import relationship
from database import Base


class AuthLevel(str, enum.Enum):
    """认证等级: basic=基础, standard=标准, advanced=高级, business=商家"""
    basic = "basic"
    standard = "standard"
    advanced = "advanced"
    business = "business"


class PostStatus(str, enum.Enum):
    published = "published"
    pending = "pending"
    rejected = "rejected"
    deleted = "deleted"


class ReportStatus(str, enum.Enum):
    pending = "pending"
    processed = "processed"
    dismissed = "dismissed"


# ========== 用户表 ==========
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    phone = Column(String(11), unique=True, nullable=False, index=True)
    id_number_hash = Column(String(64), unique=True, nullable=False)  # SHA256哈希
    face_hash = Column(String(64), unique=True, nullable=True)
    nickname = Column(String(50), nullable=False, default="韶山新邻居")
    avatar_bg = Column(String(20), nullable=True)  # 头像emoji
    auth_level = Column(Enum(AuthLevel), default=AuthLevel.basic, nullable=False)
    score = Column(Integer, default=0)  # 信誉积分
    forum_coins = Column(Integer, default=0)  # 论坛币
    last_check_in_date = Column(String(10), nullable=True)  # 上次签到日期 YYYY-MM-DD
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    is_active = Column(Boolean, default=True)
    is_frozen = Column(Boolean, default=False)
    is_super_admin = Column(Boolean, default=False)

    # 关联
    posts = relationship("Post", back_populates="author", lazy="select")
    comments = relationship("Comment", back_populates="author", lazy="select")
    likes = relationship("Like", back_populates="user", lazy="select")
    auth_documents = relationship("AuthDocument", back_populates="user", lazy="select")


# ========== 认证文件表 ==========
class AuthDocument(Base):
    __tablename__ = "auth_documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    doc_type = Column(String(20), nullable=False)  # residence_book/ business_license
    file_path = Column(String(500), nullable=False)
    status = Column(String(20), default="pending")  # pending/approved/rejected
    review_comment = Column(String(500), nullable=True)
    uploaded_at = Column(DateTime, default=datetime.now)
    reviewed_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="auth_documents")


# ========== 板块枚举 ==========
SECTION_NAMES = {
    "xinxiangshi": "韶山新鲜事",
    "chifan": "吃喝玩乐",
    "bianmin": "便民服务",
    "shuma": "数码科技",
    "jishi": "韶山集市",
    "qiuzhi": "求职招聘",
    "jiaoyu": "教育亲子",
    "xiaoqu": "小区邻里",
    "chuxing": "出行交通",
    "chaguan": "韶山茶馆",
    "jianyan": "建言献策",
}

SECTION_ICONS = {
    "xinxiangshi": "🔥", "chifan": "🍜", "bianmin": "🏥",
    "shuma": "💻", "jishi": "🛒", "qiuzhi": "👷",
    "jiaoyu": "🎓", "xiaoqu": "🏡", "chuxing": "🚌",
    "chaguan": "💬", "jianyan": "🔧",
}

SECTION_RULES = {
    "xinxiangshi": "标题须含时间+地点+事件摘要；转载须注明来源",
    "chifan": "须配3张以上实拍图；须标注人均消费；禁止商家自推伪装测评",
    "bianmin": "服务方须实名认证并上传资质证明；用户评价须真实使用后评价",
    "shuma": "技术服务方须上传相关资质证书；明码标价，提供保修承诺",
    "jishi": "明码标价，实物实拍，当场验货；禁止三无产品；涉房产须上传房产证明",
    "qiuzhi": "招聘方须上传营业执照；禁止收取任何形式的押金/培训费；薪资须明确标注",
    "jiaoyu": "培训机构评价须上传学习合同或缴费凭证佐证真实体验",
    "xiaoqu": "按小区名称发帖时须隐去具体门牌号，保护个人隐私",
    "chuxing": "拼车信息须双方实名互认后方可成行",
    "chaguan": "严禁涉政涉黄涉赌；转发外部链接须附带个人观点说明",
    "jianyan": "建议须具体可操作，禁止纯情绪发泄；投诉须附现场照片",
}


# ========== 帖子表 ==========
class Post(Base):
    __tablename__ = "posts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    section = Column(String(20), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)
    images = Column(Text, nullable=True)  # JSON数组，图片路径列表
    price_info = Column(String(100), nullable=True)
    contact_info = Column(String(100), nullable=True)
    status = Column(Enum(PostStatus), default=PostStatus.published)
    views = Column(Integer, default=0)
    likes_count = Column(Integer, default=0)
    comments_count = Column(Integer, default=0)
    is_pinned = Column(Boolean, default=False)
    pinned_at = Column(DateTime, nullable=True)  # 置顶开始时间
    pinned_expires_at = Column(DateTime, nullable=True)  # 置顶到期时间
    is_hot = Column(Boolean, default=False)  # 火热标签
    is_essential = Column(Boolean, default=False)  # 加精标签
    created_at = Column(DateTime, default=datetime.now, index=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # 关联
    author = relationship("User", back_populates="posts")
    comments = relationship("Comment", back_populates="post", lazy="select",
                           order_by="Comment.created_at.desc()", cascade="all, delete-orphan")
    likes = relationship("Like", back_populates="post", lazy="select", cascade="all, delete-orphan")


# ========== 评论表 ==========
class Comment(Base):
    __tablename__ = "comments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    post_id = Column(Integer, ForeignKey("posts.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    content = Column(Text, nullable=False)
    parent_id = Column(Integer, ForeignKey("comments.id"), nullable=True)  # 回复某条评论
    likes_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.now)

    post = relationship("Post", back_populates="comments")
    author = relationship("User", back_populates="comments")
    replies = relationship("Comment", lazy="select")


# ========== 点赞表 ==========
class Like(Base):
    __tablename__ = "likes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    post_id = Column(Integer, ForeignKey("posts.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.now)

    post = relationship("Post", back_populates="likes")
    user = relationship("User", back_populates="likes")


# ========== 举报表 ==========
class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    post_id = Column(Integer, ForeignKey("posts.id"), nullable=False)
    reporter_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    reason = Column(String(500), nullable=False)
    status = Column(Enum(ReportStatus), default=ReportStatus.pending)
    created_at = Column(DateTime, default=datetime.now)


# ========== 社区公告表 ==========
class Notice(Base):
    __tablename__ = "notices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)


# ========== 违规记录表 ==========
class Violation(Base):
    __tablename__ = "violations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    violation_type = Column(String(50), nullable=False)  # warning/mute3/mute30/ban
    reason = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    expires_at = Column(DateTime, nullable=True)  # 封禁到期时间
