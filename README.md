# VQA Annotation Tool

Flask web app for creating Visual Question Answering datasets. Admins assign images to annotators who write Q&A pairs.

## Architecture

```
[Annotators] --> [Flask App (Elastic Beanstalk)] --> [PostgreSQL (RDS)]
                         |
                   [Admin Panel]
```

- **Hosting**: AWS Elastic Beanstalk (us-east-1)
- **Database**: AWS RDS PostgreSQL
- **Auth**: Session-based with password hashing

## Database Schema

```
users
├── id (UUID, PK)
├── username (unique)
├── password_hash
├── role (admin | annotator)
└── created_at

images
├── id (TEXT, PK)
├── source, image_path, image_url
├── original_meta (JSON)
├── annotation_count
└── created_at

assignments
├── id (UUID, PK)
├── user_id (FK)
├── image_id (FK)
├── status (pending | completed)
├── assigned_at
└── completed_at

annotations
├── id (UUID, PK)
├── image_id, user_id, assignment_id (FKs)
├── question, answer
├── is_approved, is_reported
├── annotation_pass
└── annotated_at
```

## Deploying Updates

```bash
cd single_image_website
eb deploy
```

## Environment Variables

Set via `eb setenv` or AWS Console:
- `DATABASE_URL` - PostgreSQL connection string
- `SECRET_KEY` - Flask session key

## Creating Admin User

```bash
python create_admin.py <username> <password>
```

## Local Development

```bash
export DATABASE_URL="postgresql+psycopg://..."
export SECRET_KEY="dev-key"
python app.py
```
