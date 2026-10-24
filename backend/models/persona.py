from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base

if TYPE_CHECKING:
    from backend.models.audio import Audio
    from backend.models.resultado_analisis import ResultadoAnalisis


class Persona(Base):
    __tablename__ = "persona"

    id_persona: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    identificador: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    alias: Mapped[str | None] = mapped_column(String(100))
    descripcion: Mapped[str | None]
    observaciones: Mapped[str | None]
    fecha_registro: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    audios: Mapped[list["Audio"]] = relationship(back_populates="persona")
    resultados: Mapped[list["ResultadoAnalisis"]] = relationship(back_populates="persona")
