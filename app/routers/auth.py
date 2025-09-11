from fastapi import APIRouter, Depends, HTTPException, status, Header
from pydantic import BaseModel, EmailStr
from datetime import datetime, timedelta
from jose import jwt, JWTError
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from ..config import settings
from ..db import SessionLocal, User, RefreshToken, PasswordResetToken
import secrets
from collections import defaultdict

# In-memory failed login tracking (resets on restart)
_FAILED_LOGINS: dict[str, dict] = defaultdict(lambda: {"count": 0, "locked_until": None})

router = APIRouter()

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
ALGORITHM = "HS256"

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def hash_password(p: str) -> str:
    return pwd_ctx.hash(p)

def verify_password(p: str, h: str) -> bool:
    try:
        return pwd_ctx.verify(p, h)
    except Exception:
        return False

def create_access_token(data: dict, expires_minutes: int | None = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=expires_minutes or settings.access_token_expire_minutes)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.auth_secret, algorithm=ALGORITHM)

class SignupIn(BaseModel):
    email: EmailStr
    password: str

class LoginIn(BaseModel):
    email: EmailStr
    password: str

class TokenOut(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"
    role: str

class RefreshIn(BaseModel):
    refresh_token: str

class LogoutIn(BaseModel):
    refresh_token: str

class RoleUpdateIn(BaseModel):
    role: str

class CreateUserIn(BaseModel):
    email: EmailStr
    password: str
    role: str = "Normal"

class PasswordResetRequestIn(BaseModel):
    email: EmailStr

class PasswordResetConfirmIn(BaseModel):
    token: str
    new_password: str

def _normalize_role(role: str) -> str:
    valid = {"admin","Premium","Subscribe","Normal"}
    if role not in valid:
        return "Normal"
    return role

def _issue_refresh_token(db: Session, user: User) -> RefreshToken:
    # simple random URL-safe token
    token = secrets.token_urlsafe(48)
    expires = datetime.utcnow() + timedelta(days=settings.refresh_token_expire_days)
    rt = RefreshToken(user_id=user.id, token=token, expires_at=expires)
    db.add(rt)
    # prune old/expired tokens (best-effort)
    try:
        db.query(RefreshToken).filter(RefreshToken.user_id == user.id, RefreshToken.expires_at < datetime.utcnow()).delete(synchronize_session=False)
    except Exception:
        pass
    return rt

@router.post("/auth/signup", response_model=TokenOut)
def signup(body: SignupIn, db: Session = Depends(get_db)):
    if not settings.allow_self_signup:
        raise HTTPException(status_code=403, detail="signup disabled")
    exists = db.query(User).filter(User.email == body.email.lower()).one_or_none()
    if exists:
        raise HTTPException(status_code=400, detail="email in use")
    u = User(email=body.email.lower(), password_hash=hash_password(body.password), role="Normal")
    db.add(u)
    db.commit()
    db.refresh(u)
    access = create_access_token({"sub": str(u.id), "role": u.role})
    rt = _issue_refresh_token(db, u)
    db.commit()
    return TokenOut(access_token=access, refresh_token=rt.token, role=u.role)

@router.post("/auth/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    email = body.email.lower()
    # lock check
    rec = _FAILED_LOGINS[email]
    if rec["locked_until"] and rec["locked_until"] > datetime.utcnow():
        raise HTTPException(status_code=403, detail="account temporarily locked")
    u = db.query(User).filter(User.email == email).one_or_none()
    if not u or not verify_password(body.password, u.password_hash):
        rec["count"] += 1
        if rec["count"] >= settings.auth_max_failed_logins:
            rec["locked_until"] = datetime.utcnow() + timedelta(minutes=settings.auth_lock_minutes)
        raise HTTPException(status_code=400, detail="invalid credentials")
    # success -> reset counter
    _FAILED_LOGINS[email] = {"count": 0, "locked_until": None}
    access = create_access_token({"sub": str(u.id), "role": u.role})
    rt = _issue_refresh_token(db, u)
    db.commit()
    return TokenOut(access_token=access, refresh_token=rt.token, role=u.role)

def get_current_user(authorization: str | None = Header(None), db: Session = Depends(get_db)) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="not authenticated")
    token = authorization.split(" ",1)[1]
    try:
        payload = jwt.decode(token, settings.auth_secret, algorithms=[ALGORITHM])
        sub = payload.get("sub")
        role = payload.get("role")
    except JWTError:
        raise HTTPException(status_code=401, detail="invalid token")
    if not sub:
        raise HTTPException(status_code=401, detail="invalid token")
    u = db.query(User).filter(User.id == int(sub)).one_or_none()
    if not u:
        raise HTTPException(status_code=401, detail="user not found")
    if not u.is_active:
        raise HTTPException(status_code=403, detail="inactive user")
    return u

def require_role(required: str):
    order = {"Normal":1,"Subscribe":2,"Premium":3,"admin":4}
    def dep(u: User = Depends(get_current_user)):
        if order.get(u.role,0) < order.get(required,0):
            raise HTTPException(status_code=403, detail="insufficient role")
        return u
    return dep

@router.get("/auth/me")
def me(u: User = Depends(get_current_user)):
    return {"id": u.id, "email": u.email, "role": u.role}

@router.post("/auth/refresh", response_model=TokenOut)
def refresh(body: RefreshIn, db: Session = Depends(get_db)):
    rt = db.query(RefreshToken).filter(RefreshToken.token == body.refresh_token).one_or_none()
    if not rt or rt.revoked_at is not None:
        raise HTTPException(status_code=401, detail="invalid refresh token")
    if rt.expires_at < datetime.utcnow():
        raise HTTPException(status_code=401, detail="expired refresh token")
    user = db.query(User).filter(User.id == rt.user_id).one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="user not found")
    # rotate refresh token
    rt.revoked_at = datetime.utcnow()
    new_rt = _issue_refresh_token(db, user)
    access = create_access_token({"sub": str(user.id), "role": user.role})
    db.commit()
    return TokenOut(access_token=access, refresh_token=new_rt.token, role=user.role)

@router.post("/auth/logout")
def logout(body: LogoutIn, db: Session = Depends(get_db)):
    rt = db.query(RefreshToken).filter(RefreshToken.token == body.refresh_token).one_or_none()
    if not rt:
        return {"revoked": False}
    if rt.revoked_at is None:
        rt.revoked_at = datetime.utcnow()
        db.commit()
    return {"revoked": True}

@router.post("/auth/users/{user_id}/role")
def update_role(user_id: int, payload: RoleUpdateIn, admin: User = Depends(require_role("admin")), db: Session = Depends(get_db)):
    target = db.query(User).filter(User.id == user_id).one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="user not found")
    new_role = _normalize_role(payload.role)
    target.role = new_role
    db.commit()
    return {"id": target.id, "role": target.role}

@router.get("/auth/users")
def list_users(q: str | None = None, role: str | None = None, active: int | None = None, admin: User = Depends(require_role("admin")), db: Session = Depends(get_db)):
    qs = db.query(User)
    if q:
        like = f"%{q.lower()}%"
        qs = qs.filter(User.email.ilike(like))
    if role:
        qs = qs.filter(User.role == role)
    if active is not None:
        qs = qs.filter(User.is_active == (1 if active == 1 else 0))
    users = qs.order_by(User.id.asc()).all()
    return [{
        "id": u.id, "email": u.email, "role": u.role, "created_at": u.created_at.isoformat() if u.created_at else None,
        "is_active": bool(u.is_active)
    } for u in users]

@router.post("/auth/users", response_model=TokenOut | dict)
def create_user(body: CreateUserIn, admin: User = Depends(require_role("admin")), db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == body.email.lower()).one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="email exists")
    role = _normalize_role(body.role)
    u = User(email=body.email.lower(), password_hash=hash_password(body.password), role=role)
    db.add(u)
    db.commit(); db.refresh(u)
    return {"id": u.id, "email": u.email, "role": u.role, "is_active": u.is_active}

@router.post("/auth/users/{user_id}/deactivate")
def deactivate_user(user_id: int, admin: User = Depends(require_role("admin")), db: Session = Depends(get_db)):
    u = db.query(User).filter(User.id == user_id).one_or_none()
    if not u:
        raise HTTPException(status_code=404, detail="user not found")
    u.is_active = False
    db.commit()
    return {"id": u.id, "is_active": u.is_active}

@router.post("/auth/users/{user_id}/activate")
def activate_user(user_id: int, admin: User = Depends(require_role("admin")), db: Session = Depends(get_db)):
    u = db.query(User).filter(User.id == user_id).one_or_none()
    if not u:
        raise HTTPException(status_code=404, detail="user not found")
    u.is_active = True
    db.commit()
    return {"id": u.id, "is_active": u.is_active}

@router.delete("/auth/users/{user_id}")
def delete_user(user_id: int, admin: User = Depends(require_role("admin")), db: Session = Depends(get_db)):
    u = db.query(User).filter(User.id == user_id).one_or_none()
    if not u:
        raise HTTPException(status_code=404, detail="user not found")
    db.delete(u)
    db.commit()
    return {"deleted": True}

def _issue_reset_token(db: Session, user: User) -> PasswordResetToken:
    token = secrets.token_urlsafe(40)
    expires = datetime.utcnow() + timedelta(hours=2)
    rt = PasswordResetToken(user_id=user.id, token=token, expires_at=expires)
    db.add(rt)
    return rt

@router.post("/auth/password/reset-request")
def password_reset_request(body: PasswordResetRequestIn, db: Session = Depends(get_db)):
    u = db.query(User).filter(User.email == body.email.lower()).one_or_none()
    if not u:
        return {"sent": True}  # do not reveal
    t = _issue_reset_token(db, u)
    db.commit()
    # For now just return token (later: send email)
    return {"sent": True, "token": t.token}

@router.post("/auth/password/reset-confirm")
def password_reset_confirm(body: PasswordResetConfirmIn, db: Session = Depends(get_db)):
    rec = db.query(PasswordResetToken).filter(PasswordResetToken.token == body.token).one_or_none()
    if not rec or rec.used_at is not None or rec.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="invalid token")
    u = db.query(User).filter(User.id == rec.user_id).one_or_none()
    if not u:
        raise HTTPException(status_code=400, detail="invalid token")
    u.password_hash = hash_password(body.new_password)
    rec.used_at = datetime.utcnow()
    db.commit()
    return {"reset": True}
