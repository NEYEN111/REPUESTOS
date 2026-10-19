import hashlib,hmac,secrets,json,re
from datetime import datetime,timedelta
from backend.db import transaction,one,rows,now,audit

def password_hash(password):
    salt=secrets.token_hex(16)
    return salt+':'+hashlib.pbkdf2_hmac('sha256',password.encode(),salt.encode(),240000).hex()
def verify(password,encoded):
    salt,digest=encoded.split(':')
    return hmac.compare_digest(hashlib.pbkdf2_hmac('sha256',password.encode(),salt.encode(),240000).hex(),digest)
def public_user(u): return {k:v for k,v in u.items() if k!='password_hash'}
def login(email,password,admin=False):
    with transaction() as c:
        u=one(c,'SELECT * FROM users WHERE email=?',(email.strip().lower(),))
        if not u or not verify(password,u['password_hash']): raise ValueError('Correo o contraseña incorrectos.')
        if admin and u['role']=='cliente': raise ValueError('Esta cuenta no tiene acceso al panel.')
        token=secrets.token_urlsafe(32)
        c.execute('INSERT INTO sessions VALUES(?,?,?)',(token,u['id'],(datetime.fromisoformat(now())+timedelta(days=7)).isoformat()))
        return token,public_user(u)
def register(d):
    if not d.get('consent'): raise ValueError('Debes aceptar el tratamiento de tus datos personales.')
    if len(d.get('password',''))<8: raise ValueError('La contraseña debe tener al menos 8 caracteres.')
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',d.get('email','')): raise ValueError('Ingresa un correo válido.')
    if not d.get('name','').strip(): raise ValueError('Ingresa tu nombre.')
    with transaction() as c:
        if one(c,'SELECT id FROM users WHERE email=?',(d['email'].lower(),)): raise ValueError('Este correo ya está registrado.')
        c.execute('INSERT INTO users(name,email,password_hash,phone,consent_at,created_at) VALUES(?,?,?,?,?,?)',(d['name'],d['email'].lower(),password_hash(d['password']),d.get('phone',''),now(),now()))
    return login(d['email'],d['password'])
def profile(user_id,d=None):
    with transaction() as c:
        if d:
            c.execute('UPDATE users SET name=?,phone=?,document=?,billing=? WHERE id=?',(d['name'],d.get('phone',''),d.get('document',''),json.dumps(d.get('billing',{})),user_id))
        u=public_user(one(c,'SELECT * FROM users WHERE id=?',(user_id,)))
        u['billing']=json.loads(u['billing']);u['addresses']=rows(c,'SELECT * FROM addresses WHERE user_id=?',(user_id,))
        u['garage']=rows(c,'SELECT v.*,g.active FROM garage g JOIN vehicles v ON v.id=g.vehicle_id WHERE g.user_id=?',(user_id,))
        return u
