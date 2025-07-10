import sqlite3
from contextlib import contextmanager
from database_schemas import (
    USERS_TABLE_SCHEMA, 
    USER_PROFILES_TABLE_SCHEMA, 
    USER_TOPICS_TABLE_SCHEMA,
    SOCIAL_LINKS_TABLE_SCHEMA,
    COMMUNITIES_TABLE_SCHEMA,
    COMMUNITY_MEMBERS_TABLE_SCHEMA
)

DB_NAME = 'db.sqlite3'

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_NAME)
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(USERS_TABLE_SCHEMA)
        cursor.execute(USER_PROFILES_TABLE_SCHEMA)
        cursor.execute(USER_TOPICS_TABLE_SCHEMA)
        cursor.execute(SOCIAL_LINKS_TABLE_SCHEMA)
        cursor.execute(COMMUNITIES_TABLE_SCHEMA)
        cursor.execute(COMMUNITY_MEMBERS_TABLE_SCHEMA)
        from database_schemas import POSTS_TABLE_SCHEMA, POST_LIKES_TABLE_SCHEMA, POST_VIEWS_TABLE_SCHEMA, POST_MEDIA_TABLE_SCHEMA
        cursor.execute(POSTS_TABLE_SCHEMA)
        cursor.execute(POST_LIKES_TABLE_SCHEMA)
        cursor.execute(POST_VIEWS_TABLE_SCHEMA)
        cursor.execute(POST_MEDIA_TABLE_SCHEMA)
        from database_schemas import COMMENTS_TABLE_SCHEMA, COMMENT_MEDIA_TABLE_SCHEMA
        cursor.execute(COMMENTS_TABLE_SCHEMA)
        cursor.execute(COMMENT_MEDIA_TABLE_SCHEMA)
        from database_schemas import COMMENT_LIKES_TABLE_SCHEMA
        cursor.execute(COMMENT_LIKES_TABLE_SCHEMA)
        from database_schemas import COMMUNITY_POST_TAGS_TABLE_SCHEMA, POST_POST_TAGS_TABLE_SCHEMA
        cursor.execute(COMMUNITY_POST_TAGS_TABLE_SCHEMA)
        cursor.execute(POST_POST_TAGS_TABLE_SCHEMA)
        from database_schemas import MODERATION_ACTIONS_TABLE_SCHEMA
        cursor.execute(MODERATION_ACTIONS_TABLE_SCHEMA)
        conn.commit()

if __name__ == "__main__":
    init_db() 