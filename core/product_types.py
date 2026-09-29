"""
core/product_types.py

Tipos de datos para productos en el pipeline de publicación.
Facilita la comunicación entre pasos del orquestador.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any


@dataclass
class ProductDetails:
    """Datos básicos de un producto extraído por scraper."""

    id: str
    title: str
    price: float
    original_price: Optional[float] = None
    discount: str = ""  # Ej: "20%", "500 pesos"
    image_url: Optional[str] = None
    affiliate_url: Optional[str] = None
    url: str = ""
    niche: str = "[CAT:GENERAL]"

    # Banderas de validación
    is_redirected_to_lists: bool = False  # ¿Redirige a lista general?
    commission_valid: bool = True  # ¿Tiene comisión válida?

    # Metadata
    source: str = "manual"  # "mercadolibre", "amazon", "manual"
    scraped_at: Optional[str] = None

    # Metadata temporal (no se serializa) - para pasar visual_capture del scraper
    _visual_capture: Optional[str] = field(default=None, repr=False, compare=False)

    def to_dict(self) -> Dict[str, Any]:
        """Convierte a diccionario para serialización."""
        return {
            "id": self.id,
            "title": self.title,
            "price": self.price,
            "original_price": self.original_price,
            # Campos con alias para compatibilidad con message_builder
            "offer_price": f"${self.price:.2f}" if self.price else None,
            "list_price": f"${self.original_price:.2f}" if self.original_price else None,
            "discount": self.discount,
            "image_url": self.image_url,
            "affiliate_url": self.affiliate_url,
            "url": self.url,
            "niche": self.niche,
            "is_redirected_to_lists": self.is_redirected_to_lists,
            "commission_valid": self.commission_valid,
            "source": self.source,
            "scraped_at": self.scraped_at,
        }


@dataclass
class EnrichedProductDetails(ProductDetails):
    """Datos preparados y validados para publicación."""

    clean_title: str = ""  # Título limpiado por Gemini
    visual_capture: Optional[str] = None  # Ruta local de screenshot
    aff_link_verified: bool = False  # ¿Link de afiliado verificado?
    messages: Dict[str, str] = field(default_factory=dict)  # Mensajes por plataforma
    category: str = ""  # Categoría del producto (detectada por IA)
    description: str = ""  # Descripción generada por IA
    affiliate_link: str = ""  # Link de afiliado (alias de affiliate_url para compatibilidad)

    def to_dict(self) -> Dict[str, Any]:
        """Convierte a diccionario, incluyendo campos enriquecidos."""
        d = super().to_dict()
        d["visual_capture"] = self.visual_capture
        d["clean_title"] = self.clean_title
        d["category"] = self.category
        d["description"] = self.description
        d["affiliate_link"] = self.affiliate_link or self.affiliate_url
        return d

    @classmethod
    def from_details(cls, details: ProductDetails) -> "EnrichedProductDetails":
        """Crea EnrichedProductDetails a partir de ProductDetails."""
        return cls(
            id=details.id,
            title=details.title,
            price=details.price,
            original_price=details.original_price,
            discount=details.discount,
            image_url=details.image_url,
            affiliate_url=details.affiliate_url,
            url=details.url,
            niche=details.niche,
            is_redirected_to_lists=details.is_redirected_to_lists,
            commission_valid=details.commission_valid,
            source=details.source,
            scraped_at=details.scraped_at,
            clean_title=details.title,  # Inicia con el título original
            visual_capture=details._visual_capture,  # Usar visual_capture del scraper si existe
            affiliate_link=details.affiliate_url or "",  # Alias de affiliate_url
        )


@dataclass
class PublicationResult:
    """Resultado de publicación en una plataforma."""

    platform: str  # "facebook", "pinterest", "telegram", etc.
    success: bool
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    error: Optional[Exception] = None

    def __str__(self):
        status = "✅" if self.success else "❌"
        return f"{status} {self.platform}: {self.message}"


@dataclass
class PublicationResults:
    """Resultados agregados de publicación en todas las plataformas."""

    product_id: str
    results: Dict[str, PublicationResult] = field(default_factory=dict)
    overall_success: bool = False

    def add_result(self, result: PublicationResult):
        """Agregar resultado de una plataforma."""
        self.results[result.platform] = result

    def get_summary(self) -> str:
        """Resumen de resultados para reportar."""
        lines = []
        for platform, result in self.results.items():
            lines.append(str(result))
        return "\n".join(lines)

    @property
    def success_count(self) -> int:
        """Cantidad de plataformas donde fue exitoso."""
        return sum(1 for r in self.results.values() if r.success)

    @property
    def total_count(self) -> int:
        """Total de plataformas intentadas."""
        return len(self.results)
