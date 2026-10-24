from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base

if TYPE_CHECKING:
    from backend.models.embedding import Embedding
    from backend.models.persona import Persona
    from backend.models.usuario import Usuario


class Audio(Base):
    __tablename__ = "audio"
    __table_args__ = (
        CheckConstraint(
            "formato_original IN ('mp3', 'ogg', 'mp4', 'wav')",
            name="ck_audio_formato_original",
        ),
        CheckConstraint(
            "duracion_segundos IS NULL OR duracion_segundos > 0",
            name="ck_audio_duracion_positiva",
        ),
    )

    id_audio: Mapped[int] = mapped_column(primary_key=True)
    id_persona: Mapped[int] = mapped_column(
        ForeignKey("voxtrace.persona.id_persona", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=False,
    )
    id_usuario: Mapped[int] = mapped_column(
        ForeignKey("voxtrace.usuario.id_usuario", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=False,
    )
    ruta_archivo: Mapped[str] = mapped_column(String(500), nullable=False)
    nombre_original: Mapped[str] = mapped_column(String(255), nullable=False)
    formato_original: Mapped[str] = mapped_column(String(20), nullable=False)
    duracion_segundos: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    hash_archivo: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    fecha_subida: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    persona: Mapped["Persona"] = relationship(back_populates="audios")
    usuario: Mapped["Usuario"] = relationship(back_populates="audios")
    embedding: Mapped["Embedding | None"] = relationship(
        back_populates="audio",
        uselist=False,
        cascade="all, delete-orphan",
    )
