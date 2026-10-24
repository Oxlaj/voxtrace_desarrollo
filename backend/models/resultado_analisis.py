from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base

if TYPE_CHECKING:
    from backend.models.analisis import Analisis
    from backend.models.persona import Persona


class ResultadoAnalisis(Base):
    __tablename__ = "resultado_analisis"
    __table_args__ = (
        CheckConstraint("similitud >= 0 AND similitud <= 100", name="ck_resultado_similitud_rango"),
        CheckConstraint("posicion > 0", name="ck_resultado_posicion_positiva"),
        UniqueConstraint("id_analisis", "id_persona", name="uq_resultado_analisis_persona"),
        UniqueConstraint("id_analisis", "posicion", name="uq_resultado_analisis_posicion"),
    )

    id_resultado: Mapped[int] = mapped_column(primary_key=True)
    id_analisis: Mapped[int] = mapped_column(
        ForeignKey("voxtrace.analisis.id_analisis", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=False,
    )
    id_persona: Mapped[int] = mapped_column(
        ForeignKey("voxtrace.persona.id_persona", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=False,
    )
    similitud: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False)
    posicion: Mapped[int] = mapped_column(nullable=False)
    supera_umbral: Mapped[bool] = mapped_column(nullable=False, server_default="false")

    analisis: Mapped["Analisis"] = relationship(back_populates="resultados")
    persona: Mapped["Persona"] = relationship(back_populates="resultados")
