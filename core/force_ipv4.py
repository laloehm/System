"""
Fuerza resolución DNS solo-IPv4 para todo el proceso que lo importe.

Por qué: el servidor tiene IPv6 anunciado pero sin ruta real a internet.
`urllib` (usado en web_publisher.py para hablar con la API de GitHub) no hace
fallback a IPv4 y falla con "Network is unreachable" casi en cada intento
contra hosts con registro AAAA. `aiohttp` (Telegram) sí reintenta, pero agota
el timeout completo en el intento IPv6 antes de caer a IPv4. Forzar IPv4 aquí
evita ambos casos sin depender de la configuración de red del host.
"""
import socket

_original_getaddrinfo = socket.getaddrinfo


def _ipv4_only_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    return _original_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)


socket.getaddrinfo = _ipv4_only_getaddrinfo
