from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base

if TYPE_CHECKING:
    from backend.models.usuario import Usuario


class Log(Base):
    __tablename__ = "log"

    id_log: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    id_usuario: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("voxtrace.usuario.id_usuario", onupdate="CASCADE", ondelete="SET NULL"),
    )
    accion: Mapped[str] = mapped_column(String(150), nullable=False)
    fecha: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    direccion_ip: Mapped[str | None] = mapped_column(String(45))
    detalles: Mapped[str | None] = mapped_column(Text)

    usuario: Mapped["Usuario | None"] = relationship(back_populates="logs")
