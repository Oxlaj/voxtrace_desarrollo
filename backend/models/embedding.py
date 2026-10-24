from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base

if TYPE_CHECKING:
    from backend.models.audio import Audio


class Embedding(Base):
    __tablename__ = "embedding"

    id_embedding: Mapped[int] = mapped_column(primary_key=True)
    id_audio: Mapped[int] = mapped_column(
        ForeignKey("voxtrace.audio.id_audio", onupdate="CASCADE", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    vector: Mapped[str] = mapped_column(Text, nullable=False)
    modelo_utilizado: Mapped[str] = mapped_column(String(150), nullable=False)
    fecha_generacion: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    audio: Mapped["Audio"] = relationship(back_populates="embedding")
