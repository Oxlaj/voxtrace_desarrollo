from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base

if TYPE_CHECKING:
    from backend.models.resultado_analisis import ResultadoAnalisis
    from backend.models.usuario import Usuario


class Analisis(Base):
    __tablename__ = "analisis"
    __table_args__ = (
        CheckConstraint(
            "formato_original IN ('mp3', 'ogg', 'mp4', 'wav')",
            name="ck_analisis_formato_original",
        ),
        CheckConstraint(
            "estado IN ('pendiente', 'procesando', 'completado', 'error')",
            name="ck_analisis_estado",
        ),
    )

    id_analisis: Mapped[int] = mapped_column(primary_key=True)
    id_usuario: Mapped[int] = mapped_column(
        ForeignKey("voxtrace.usuario.id_usuario", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=False,
    )
    ruta_audio_consulta: Mapped[str] = mapped_column(String(500), nullable=False)
    nombre_original: Mapped[str] = mapped_column(String(255), nullable=False)
    formato_original: Mapped[str] = mapped_column(String(20), nullable=False)
    hash_audio_consulta: Mapped[str] = mapped_column(String(128), nullable=False)
    fecha_analisis: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    estado: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        server_default=text("'completado'"),
    )

    usuario: Mapped["Usuario"] = relationship(back_populates="analisis")
    resultados: Mapped[list["ResultadoAnalisis"]] = relationship(back_populates="analisis")
