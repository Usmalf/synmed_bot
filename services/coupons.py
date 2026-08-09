from __future__ import annotations

from datetime import datetime, timezone

from database import get_connection


UTC = timezone.utc
VALID_PURPOSES = {"registration", "consultation", "both"}
VALID_DISCOUNT_TYPES = {"free", "percent", "fixed"}


class CouponError(Exception):
    pass


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _parse_iso(value: str | None):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    except ValueError:
        return None


def normalize_coupon_code(code: str | None) -> str:
    return "".join((code or "").strip().upper().split())


def _coupon_to_dict(row) -> dict | None:
    if not row:
        return None
    coupon = dict(row)
    configured_active = bool(coupon.get("active"))
    expires_at = _parse_iso(coupon.get("expires_at"))
    expired = bool(expires_at and datetime.now(UTC) > expires_at)
    coupon["configured_active"] = configured_active
    coupon["expired"] = expired
    coupon["active"] = configured_active and not expired
    coupon["used_count"] = int(coupon.get("used_count") or 0)
    return coupon


def get_coupon(code: str) -> dict | None:
    normalized = normalize_coupon_code(code)
    if not normalized:
        return None
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT c.*,
                   COALESCE((SELECT COUNT(*) FROM coupon_redemptions r WHERE UPPER(r.coupon_code) = UPPER(c.code)), 0) AS used_count
            FROM coupons c
            WHERE UPPER(c.code) = UPPER(?)
            """,
            (normalized,),
        )
        return _coupon_to_dict(cursor.fetchone())


def list_coupons(limit: int = 100) -> list[dict]:
    safe_limit = max(1, min(int(limit or 100), 250))
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT c.*,
                   COALESCE((SELECT COUNT(*) FROM coupon_redemptions r WHERE UPPER(r.coupon_code) = UPPER(c.code)), 0) AS used_count
            FROM coupons c
            ORDER BY datetime(c.created_at) DESC, c.id DESC
            LIMIT ?
            """,
            (safe_limit,),
        )
        return [_coupon_to_dict(row) for row in cursor.fetchall()]


def list_coupon_redemptions(code: str = "", limit: int = 100) -> list[dict]:
    safe_limit = max(1, min(int(limit or 100), 250))
    normalized = normalize_coupon_code(code)
    with get_connection() as conn:
        cursor = conn.cursor()
        if normalized:
            cursor.execute(
                """
                SELECT *
                FROM coupon_redemptions
                WHERE UPPER(coupon_code) = UPPER(?)
                ORDER BY datetime(redeemed_at) DESC, id DESC
                LIMIT ?
                """,
                (normalized, safe_limit),
            )
        else:
            cursor.execute(
                """
                SELECT *
                FROM coupon_redemptions
                ORDER BY datetime(redeemed_at) DESC, id DESC
                LIMIT ?
                """,
                (safe_limit,),
            )
        return [dict(row) for row in cursor.fetchall()]


def has_active_coupon_for_purpose(purpose: str) -> bool:
    normalized_purpose = (purpose or "").strip().lower()
    if normalized_purpose not in {"registration", "consultation"}:
        return False
    now = _now_iso()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT c.code,
                   COALESCE((SELECT COUNT(*) FROM coupon_redemptions r WHERE UPPER(r.coupon_code) = UPPER(c.code)), 0) AS used_count
            FROM coupons c
            WHERE c.active = 1
              AND c.applies_to IN (?, 'both')
              AND (c.expires_at IS NULL OR c.expires_at = '' OR c.expires_at > ?)
              AND (c.max_uses IS NULL OR c.max_uses > COALESCE((SELECT COUNT(*) FROM coupon_redemptions r WHERE UPPER(r.coupon_code) = UPPER(c.code)), 0))
            LIMIT 1
            """,
            (normalized_purpose, now),
        )
        return cursor.fetchone() is not None


def create_coupon(payload: dict, *, admin_id: str | int | None = None) -> dict:
    code = normalize_coupon_code(payload.get("code"))
    if len(code) < 3:
        raise CouponError("Enter a coupon code with at least 3 characters.")

    applies_to = (payload.get("applies_to") or "both").strip().lower()
    if applies_to not in VALID_PURPOSES:
        raise CouponError("Coupon must apply to registration, consultation, or both.")

    discount_type = (payload.get("discount_type") or "percent").strip().lower()
    if discount_type not in VALID_DISCOUNT_TYPES:
        raise CouponError("Coupon discount type must be free, percent, or fixed.")

    try:
        discount_value = int(payload.get("discount_value") or 0)
        max_uses = payload.get("max_uses")
        per_user_limit = int(payload.get("per_user_limit") or 1)
    except (TypeError, ValueError) as exc:
        raise CouponError("Coupon values must be valid numbers.") from exc

    if discount_type == "free":
        discount_value = 100
    elif discount_type == "percent" and not 1 <= discount_value <= 100:
        raise CouponError("Percent coupons must be between 1 and 100.")
    elif discount_type == "fixed" and discount_value < 1:
        raise CouponError("Fixed amount coupons must be greater than zero.")

    max_uses_value = None
    if max_uses not in {None, ""}:
        max_uses_value = max(1, int(max_uses))
    per_user_limit = max(1, per_user_limit)
    expires_at = (payload.get("expires_at") or "").strip() or None
    if expires_at and not _parse_iso(expires_at):
        raise CouponError("Coupon expiry date is invalid.")

    now = _now_iso()
    with get_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO coupons (
                    code, description, applies_to, discount_type, discount_value,
                    max_uses, per_user_limit, expires_at, active, created_by_admin_id,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    code,
                    (payload.get("description") or "").strip(),
                    applies_to,
                    discount_type,
                    discount_value,
                    max_uses_value,
                    per_user_limit,
                    expires_at,
                    1 if payload.get("active", True) else 0,
                    str(admin_id or ""),
                    now,
                    now,
                ),
            )
            conn.commit()
        except Exception as exc:
            conn.rollback()
            raise CouponError("A coupon with this code already exists.") from exc
    return get_coupon(code) or {}


def update_coupon_status(code: str, active: bool) -> dict:
    normalized = normalize_coupon_code(code)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE coupons
            SET active = ?, updated_at = ?
            WHERE UPPER(code) = UPPER(?)
            """,
            (1 if active else 0, _now_iso(), normalized),
        )
        updated = cursor.rowcount > 0
        conn.commit()
    if not updated:
        raise CouponError("Coupon could not be found.")
    return get_coupon(normalized) or {}


def _identity_redemption_count(cursor, coupon_code: str, patient_id: str, email: str, phone: str) -> int:
    clauses = []
    params = [coupon_code]
    if patient_id:
        clauses.append("UPPER(COALESCE(patient_id, '')) = UPPER(?)")
        params.append(patient_id)
    if email:
        clauses.append("LOWER(COALESCE(email, '')) = LOWER(?)")
        params.append(email)
    if phone:
        clauses.append("COALESCE(phone, '') = ?")
        params.append(phone)
    if not clauses:
        return 0
    cursor.execute(
        f"""
        SELECT COUNT(*) AS count
        FROM coupon_redemptions
        WHERE UPPER(coupon_code) = UPPER(?)
          AND ({" OR ".join(clauses)})
        """,
        tuple(params),
    )
    row = cursor.fetchone()
    return int(row["count"] if row else 0)


def validate_coupon(
    *,
    code: str,
    purpose: str,
    amount: int,
    patient_id: str = "",
    email: str = "",
    phone: str = "",
) -> dict:
    normalized = normalize_coupon_code(code)
    if not normalized:
        return {
            "applied": False,
            "code": "",
            "discount_amount": 0,
            "amount_before": amount,
            "amount_after": amount,
            "message": "",
        }

    purpose = (purpose or "").strip().lower()
    if purpose not in {"registration", "consultation"}:
        raise CouponError("Coupon cannot be applied to this payment type.")

    coupon = get_coupon(normalized)
    if not coupon:
        raise CouponError("Coupon code was not found.")
    if not coupon["active"]:
        raise CouponError("This coupon is no longer active.")
    if coupon["applies_to"] not in {purpose, "both"}:
        raise CouponError("This coupon cannot be used for this payment.")

    expires_at = _parse_iso(coupon.get("expires_at"))
    if expires_at and datetime.now(UTC) > expires_at:
        raise CouponError("This coupon has expired.")
    if coupon.get("max_uses") is not None and coupon["used_count"] >= int(coupon["max_uses"]):
        raise CouponError("This coupon has reached its usage limit.")

    with get_connection() as conn:
        cursor = conn.cursor()
        identity_count = _identity_redemption_count(cursor, normalized, patient_id, email, phone)
    if identity_count >= int(coupon.get("per_user_limit") or 1):
        raise CouponError("This coupon has already been used for this account.")

    amount_before = max(0, int(amount or 0))
    if coupon["discount_type"] == "free":
        discount = amount_before
    elif coupon["discount_type"] == "percent":
        discount = (amount_before * int(coupon["discount_value"])) // 100
    else:
        discount = int(coupon["discount_value"])
    discount = max(0, min(discount, amount_before))
    amount_after = max(0, amount_before - discount)
    return {
        "applied": True,
        "coupon": coupon,
        "code": normalized,
        "purpose": purpose,
        "discount_amount": discount,
        "amount_before": amount_before,
        "amount_after": amount_after,
        "message": f"Coupon {normalized} applied.",
    }


def record_coupon_redemption(
    *,
    reference: str,
    code: str,
    purpose: str,
    amount_before: int,
    discount_amount: int,
    amount_after: int,
    patient_id: str = "",
    email: str = "",
    phone: str = "",
) -> bool:
    normalized = normalize_coupon_code(code)
    if not normalized or not reference:
        return False
    with get_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO coupon_redemptions (
                    coupon_code, reference, patient_id, email, phone, purpose,
                    amount_before, discount_amount, amount_after, redeemed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    normalized,
                    reference,
                    patient_id or "",
                    email or "",
                    phone or "",
                    purpose,
                    int(amount_before or 0),
                    int(discount_amount or 0),
                    int(amount_after or 0),
                    _now_iso(),
                ),
            )
            conn.commit()
            return True
        except Exception:
            conn.rollback()
            return False
