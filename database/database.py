from sqlalchemy import ForeignKey, String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Session, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Tree(Base):
    __tablename__ = "tree"
    qid: Mapped[int] = mapped_column(ForeignKey('data.id'), primary_key=True)
    pid: Mapped[int] = mapped_column(ForeignKey('tree.pid'))
    properties: Mapped[str] = mapped_column()

class Data(Base):
    __tablename__ = "data"
    id: Mapped[int] = mapped_column(primary_key=True)
    text: Mapped[str] = mapped_column()
    
class Images(Base):
    __tablename__ = "images"
    id: Mapped[int] = mapped_column(ForeignKey('data.id'), primary_key=True)
    image: Mapped[str] = mapped_column()
    
class Poll(Base):
    __tablename__ = "poll"
    id: Mapped[int] = mapped_column(primary_key=True)
    question: Mapped[str] = mapped_column()
    passed: Mapped[str] = mapped_column(default='')
    children = relationship('PollOptions', back_populates='parent', cascade='all, delete', passive_deletes=True)
    
class PollOptions(Base):
    __tablename__ = "poll_options"
    id: Mapped[int] = mapped_column(primary_key=True)
    pid: Mapped[int] = mapped_column(ForeignKey('poll.id', ondelete='CASCADE'))
    option: Mapped[str] = mapped_column()
    count: Mapped[int] = mapped_column(default=0)
    parent = relationship('Poll', back_populates='children')

class Admins(Base):
    __tablename__ = "admins"
    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column()
    
engine = create_engine("sqlite:///database/data.db")


session = Session(engine)

query = select(Tree.qid).where(Tree.pid == 2)
