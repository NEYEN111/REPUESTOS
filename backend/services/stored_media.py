"""Small uploaded images stored with transactional business data."""
import io
import secrets

from PIL import Image, UnidentifiedImageError

from backend.db import one, now


async def prepare(file):
    raw = await file.read(8 * 1024 * 1024 + 1)
    if len(raw) > 8 * 1024 * 1024:
        raise ValueError('La imagen supera los 8 MB.')
    try:
        image = Image.open(io.BytesIO(raw))
        image.load()
        if image.width * image.height > 25_000_000:
            raise ValueError('La imagen es demasiado grande.')
        image = image.convert('RGB')
        image.thumbnail((1400, 1400))
        large = io.BytesIO()
        image.save(large, 'WEBP', quality=88)
        image.thumbnail((360, 360))
        thumb = io.BytesIO()
        image.save(thumb, 'WEBP', quality=85)
    except (UnidentifiedImageError, OSError):
        raise ValueError('Adjunta una imagen JPG, PNG o WebP válida.') from None
    return large.getvalue(), thumb.getvalue()


def save(c, kind, content):
    name = secrets.token_hex(16) + '.webp'
    c.execute('INSERT INTO stored_media(name,kind,content,created_at) VALUES(?,?,?,?)',
              (name, kind, content, now()))
    return name


def read(c, name, kind):
    return one(c, 'SELECT content FROM stored_media WHERE name=? AND kind=?', (name, kind))


def remove(c, url):
    prefix = '/api/media/'
    if url.startswith(prefix):
        c.execute("DELETE FROM stored_media WHERE name=? AND kind='product'", (url[len(prefix):],))
