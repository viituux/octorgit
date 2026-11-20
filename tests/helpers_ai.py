from octorgit.ai_engine import CATEGORIES


def structured_response(context=None):
    return {"sections": [{"title": title, "claims": [{"text": "Não confirmado neste contexto: " + title.lower() + ".", "confidence": "unconfirmed", "evidence_ids": []}]} for _, title, _ in CATEGORIES]}
