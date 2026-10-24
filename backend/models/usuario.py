from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base

if TYPE_CHECKING:
    from backend.models.analisis import Analisis
    from backend.models.audio import Audio
    from backend.models.log import Log
    from backend.models.rol import Rol


class Usuario(Base):
    __tablename__ = "usuario"

    id_usuario: Mapped[int] = mapped_column(primary_key=True)
    id_rol: Mapped[int] = mapped_column(
        ForeignKey("voxtrace.rol.id_rol", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=False,
    )
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    correo: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    estado: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("TRUE"))
    debe_cambiar_password: Mapped[bool] = mapped_column(
    Boolean,
    nullable=False,
    server_default=text("FALSE"),
)

    rol: Mapped["Rol"] = relationship(back_populates="usuarios")
    audios: Mapped[list["Audio"]] = relationship(back_populates="usuario")
    analisis: Mapped[list["Analisis"]] = relationship(back_populates="usuario")
    logs: Mapped[list["Log"]] = relationship(back_populates="usuario")
