# UPLAS Platform - Backend

This is the Django backend for the UPLAS (Universal Platform for Learning and Skills) project.

## Project Overview

The UPLAS platform aims to provide a comprehensive e-learning experience with features including:
- User Authentication and Profiles
- Course Management (Categories, Courses, Modules, Topics, Quizzes)
- User Enrollment and Progress Tracking
- Payments and Subscriptions (via Stripe)
- Real-world Projects with AI Assessment
- Community Forums
- Blog
- AI-powered Tutors, Text-to-Speech, and Text-to-Video features (via separate AI services).

## Tech Stack

-   **Backend:** Django, Django REST Framework
-   **Database:** Cloud SQL for MySQL (on GCP)
-   **Authentication:** JWT (SimpleJWT)
-   **Deployment:** Google Cloud Platform (e.g., Cloud Run or App Engine)
-   **External AI Services:** Separate repository `uplas-ai-services` handles AI logic. This backend acts as an API client.

## Setup and Installation (Conceptual for Cloud Development)

1.  **Prerequisites:**
    * Google Cloud SDK configured
    * Access to a GCP project
    * Python 3.9+
    * `pip`
2.  **Environment Variables:**
    * See `.env.example` (you should create this) for required variables (DB, SECRET_KEY, GCP, Stripe, AI Service URLs).
    * Use `.env` for local development. Set in GCP for production.
3.  **Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
4.  **Database Migrations:**
    ```bash
    python manage.py migrate
    ```
5.  **Run Development Server:**
    ```bash
    python manage.py runserver
    ```

## API Endpoints

The API endpoints are structured under `/api/`. Refer to `uplas_project/urls.py` and app-specific `urls.py` files. The API root is at `/api/core/`.

## Directory Structure

-   `uplas_project/`: Main Django project configuration.
-   `apps/`: Contains individual Django applications.
-   `.github/workflows/`: CI/CD workflows.
-   `requirements.txt`: Python dependencies.
-   `manage.py`: Django's command-line utility.

---
