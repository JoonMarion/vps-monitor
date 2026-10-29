"""Persistent accounts and VPS ownership. SSH secrets never leave the backend."""

import datetime
import json
import uuid

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


def new_id():
    return str(uuid.uuid4())


def utcnow():
    return datetime.datetime.now(datetime.timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    def public_data(self):
        return {"id": self.id, "name": self.name, "email": self.email}


class VPSServer(Base):
    __tablename__ = "vps_servers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    ip: Mapped[str] = mapped_column(String(45))
    port: Mapped[int] = mapped_column(Integer, default=22)
    location: Mapped[str] = mapped_column(String(100))
    ssh_user: Mapped[str] = mapped_column(String(100))
    encrypted_credentials: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    def public_data(self):
        return {
            "id": self.id, "name": self.name, "ip": self.ip, "port": self.port,
            "location": self.location, "user": self.ssh_user,
        }

    def connection_data(self, cipher):
        credentials = json.loads(cipher.decrypt(self.encrypted_credentials.encode()).decode())
        return {**self.public_data(), **credentials}


def create_database(database_url, *, initialize=True):
    url = make_url(database_url)
    if url.drivername in {"postgres", "postgresql"}:
        url = url.set(drivername="postgresql+psycopg")
    engine = create_engine(url, pool_pre_ping=True, hide_parameters=True)
    if initialize:
        Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine, expire_on_commit=False)
