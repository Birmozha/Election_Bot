from sqlalchemy import ForeignKey, String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Session, Mapped, mapped_column


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


engine = create_engine("sqlite:///database/data.db")


session = Session(engine)

query = select(Tree.qid).where(Tree.pid == 2)
