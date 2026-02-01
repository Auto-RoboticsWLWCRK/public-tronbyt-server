# Supabase Multi-Tenant Architecture for Tronbyt Server

This document provides comprehensive guidance for deploying Tronbyt Server as a public, multi-user service on **Render** using **Supabase** as the backend database and auth provider.

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Supabase Schema](#supabase-schema)
3. [Render Environment Variables](#render-environment-variables)
4. [File-by-File Guide](#file-by-file-guide)
5. [Code Examples](#code-examples)
6. [Deployment Checklist](#deployment-checklist)

---

## Architecture Overview

### What Changes

| Component | Before (SQLite) | After (Supabase) |
|-----------|-----------------|------------------|
| **Database** | SQLite file (`users/usersdb.sqlite`) | Supabase PostgreSQL |
| **Authentication** | `fastapi-login` with password hashes | Supabase Auth (email/password) |
| **Session Management** | JWT tokens via `LoginManager` | Supabase session tokens |
| **User Storage** | JSON blob in SQLite | Normalized Postgres tables |
| **Device Ownership** | Implicit (user JSON contains devices) | Explicit `user_id` foreign key |
| **API Keys** | Stored in user JSON | Dedicated `api_tokens` table |
| **File Storage** | Local disk (`data/webp/`) | Supabase Storage (optional) or Render Disk |

### What Stays the Same

- FastAPI application structure
- All existing routes (wrapped with new auth)
- Pixlet rendering logic
- Device firmware communication protocol
- Frontend templates (minimal changes for auth)
- WebSocket functionality

### Multi-Tenancy Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Render Web Service                       │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                    FastAPI Application                       │ │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │ │
│  │  │ Auth Router │  │ API Router  │  │   Manager Router    │  │ │
│  │  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘  │ │
│  │         │                │                     │             │ │
│  │         └────────────────┴─────────────────────┘             │ │
│  │                          │                                   │ │
│  │              ┌───────────┴───────────┐                       │ │
│  │              │   Supabase Middleware │                       │ │
│  │              │   (Auth + RLS)        │                       │ │
│  │              └───────────┬───────────┘                       │ │
│  └──────────────────────────┼───────────────────────────────────┘ │
└──────────────────────────────┼───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                         Supabase                                  │
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────────┐  │
│  │   Supabase Auth │  │ PostgreSQL + RLS│  │ Supabase Storage │  │
│  │   (Email/Pass)  │  │   (All Data)    │  │   (WebP Images)  │  │
│  └─────────────────┘  └─────────────────┘  └──────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

---

## Supabase Schema

### Tables

Execute these SQL statements in your Supabase SQL Editor:

```sql
-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================
-- USERS TABLE (extends Supabase auth.users)
-- ============================================
CREATE TABLE public.user_profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    username TEXT UNIQUE NOT NULL CHECK (username ~ '^[A-Za-z0-9_-]+$'),
    email TEXT,
    theme_preference TEXT DEFAULT 'system' CHECK (theme_preference IN ('light', 'dark', 'system')),
    system_repo_url TEXT DEFAULT '',
    app_repo_url TEXT DEFAULT '',
    is_admin BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- API TOKENS TABLE
-- ============================================
CREATE TABLE public.api_tokens (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES public.user_profiles(id) ON DELETE CASCADE,
    token TEXT UNIQUE NOT NULL,
    name TEXT DEFAULT 'Default',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_used_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ
);

CREATE INDEX idx_api_tokens_token ON public.api_tokens(token);
CREATE INDEX idx_api_tokens_user_id ON public.api_tokens(user_id);

-- ============================================
-- DEVICES TABLE
-- ============================================
CREATE TABLE public.devices (
    id TEXT PRIMARY KEY CHECK (id ~ '^[a-fA-F0-9]{8}$'),
    user_id UUID NOT NULL REFERENCES public.user_profiles(id) ON DELETE CASCADE,
    name TEXT DEFAULT '',
    type TEXT DEFAULT 'tidbyt_gen1' CHECK (type IN (
        'tidbyt_gen1', 'tidbyt_gen2', 'pixoticker', 
        'raspberrypi', 'tronbyt_s3', 'tronbyt_s3_wide', 'other'
    )),
    api_key TEXT DEFAULT '',
    img_url TEXT DEFAULT '',
    ws_url TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    brightness INTEGER DEFAULT 100 CHECK (brightness >= 0 AND brightness <= 100),
    night_mode_enabled BOOLEAN DEFAULT FALSE,
    night_mode_app TEXT DEFAULT '',
    night_start TEXT,
    night_end TEXT,
    night_brightness INTEGER DEFAULT 0 CHECK (night_brightness >= 0 AND night_brightness <= 100),
    dim_time TEXT,
    dim_brightness INTEGER CHECK (dim_brightness IS NULL OR (dim_brightness >= 0 AND dim_brightness <= 100)),
    default_interval INTEGER DEFAULT 15 CHECK (default_interval >= 0),
    timezone TEXT,
    location JSONB,
    last_app_index INTEGER DEFAULT 0,
    pinned_app TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_devices_user_id ON public.devices(user_id);
CREATE INDEX idx_devices_api_key ON public.devices(api_key) WHERE api_key != '';

-- ============================================
-- APPS TABLE (App Installations)
-- ============================================
CREATE TABLE public.app_installations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    device_id TEXT NOT NULL REFERENCES public.devices(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES public.user_profiles(id) ON DELETE CASCADE,
    iname TEXT NOT NULL,  -- Installation name (unique per device)
    name TEXT NOT NULL,   -- App name
    path TEXT DEFAULT '',
    enabled BOOLEAN DEFAULT TRUE,
    uinterval INTEGER DEFAULT 0,
    display_time INTEGER DEFAULT 0,
    config JSONB DEFAULT '{}',
    last_render BIGINT DEFAULT 0,
    empty_last_render BOOLEAN DEFAULT FALSE,
    pushed BOOLEAN DEFAULT FALSE,
    notes TEXT DEFAULT '',
    schedule JSONB DEFAULT '{}',
    recurrence_pattern JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(device_id, iname)
);

CREATE INDEX idx_app_installations_device_id ON public.app_installations(device_id);
CREATE INDEX idx_app_installations_user_id ON public.app_installations(user_id);

-- ============================================
-- DEVICE PAIRING TOKENS TABLE
-- ============================================
CREATE TABLE public.device_pairing_tokens (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    device_id TEXT UNIQUE NOT NULL CHECK (device_id ~ '^[a-fA-F0-9]{8}$'),
    token TEXT UNIQUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    claimed_by UUID REFERENCES public.user_profiles(id),
    claimed_at TIMESTAMPTZ
);

CREATE INDEX idx_pairing_tokens_token ON public.device_pairing_tokens(token);
CREATE INDEX idx_pairing_tokens_expires ON public.device_pairing_tokens(expires_at);

-- ============================================
-- SCHEMA METADATA TABLE
-- ============================================
CREATE TABLE public.meta (
    id INTEGER PRIMARY KEY DEFAULT 1,
    schema_version INTEGER NOT NULL DEFAULT 1
);

INSERT INTO public.meta (schema_version) VALUES (1);
```

### Row Level Security (RLS) Policies

```sql
-- Enable RLS on all tables
ALTER TABLE public.user_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.api_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.devices ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.app_installations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.device_pairing_tokens ENABLE ROW LEVEL SECURITY;

-- ============================================
-- USER PROFILES POLICIES
-- ============================================
-- Users can only read their own profile
CREATE POLICY "Users can view own profile" ON public.user_profiles
    FOR SELECT USING (auth.uid() = id);

-- Users can update their own profile
CREATE POLICY "Users can update own profile" ON public.user_profiles
    FOR UPDATE USING (auth.uid() = id);

-- Allow profile creation on signup (via trigger)
CREATE POLICY "Enable insert for authenticated users only" ON public.user_profiles
    FOR INSERT WITH CHECK (auth.uid() = id);

-- ============================================
-- API TOKENS POLICIES
-- ============================================
CREATE POLICY "Users can view own API tokens" ON public.api_tokens
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can create own API tokens" ON public.api_tokens
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own API tokens" ON public.api_tokens
    FOR UPDATE USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own API tokens" ON public.api_tokens
    FOR DELETE USING (auth.uid() = user_id);

-- ============================================
-- DEVICES POLICIES
-- ============================================
CREATE POLICY "Users can view own devices" ON public.devices
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can create own devices" ON public.devices
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own devices" ON public.devices
    FOR UPDATE USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own devices" ON public.devices
    FOR DELETE USING (auth.uid() = user_id);

-- ============================================
-- APP INSTALLATIONS POLICIES
-- ============================================
CREATE POLICY "Users can view own app installations" ON public.app_installations
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can create own app installations" ON public.app_installations
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own app installations" ON public.app_installations
    FOR UPDATE USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own app installations" ON public.app_installations
    FOR DELETE USING (auth.uid() = user_id);

-- ============================================
-- DEVICE PAIRING TOKENS POLICIES
-- ============================================
-- Anyone can view unclaimed tokens (for claiming)
CREATE POLICY "Anyone can view unclaimed tokens" ON public.device_pairing_tokens
    FOR SELECT USING (claimed_by IS NULL AND expires_at > NOW());

-- Authenticated users can claim tokens
CREATE POLICY "Authenticated users can claim tokens" ON public.device_pairing_tokens
    FOR UPDATE USING (
        auth.uid() IS NOT NULL 
        AND claimed_by IS NULL 
        AND expires_at > NOW()
    );

-- Service role can insert tokens (from firmware)
-- Note: This requires using service_role key for firmware endpoints
```

### Triggers

```sql
-- ============================================
-- AUTO-CREATE USER PROFILE ON SIGNUP
-- ============================================
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.user_profiles (id, username, email)
    VALUES (
        NEW.id,
        COALESCE(NEW.raw_user_meta_data->>'username', SPLIT_PART(NEW.email, '@', 1)),
        NEW.email
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- ============================================
-- AUTO-UPDATE TIMESTAMPS
-- ============================================
CREATE OR REPLACE FUNCTION public.update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_user_profiles_updated_at
    BEFORE UPDATE ON public.user_profiles
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();

CREATE TRIGGER update_devices_updated_at
    BEFORE UPDATE ON public.devices
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();

CREATE TRIGGER update_app_installations_updated_at
    BEFORE UPDATE ON public.app_installations
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();
```

---

## Render Environment Variables

### Required Variables

| Variable | Description | Safe to Hardcode? |
|----------|-------------|-------------------|
| `SUPABASE_URL` | Your Supabase project URL (e.g., `https://xxx.supabase.co`) | No - **MUST** be env var |
| `SUPABASE_ANON_KEY` | Supabase anonymous/public key | No - **MUST** be env var |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role key (for server-side operations) | No - **MUST** be env var |
| `SECRET_KEY` | FastAPI session secret | No - **MUST** be env var |

### Optional Variables

| Variable | Description | Default | Safe to Hardcode? |
|----------|-------------|---------|-------------------|
| `AUTH_MODE` | Authentication mode (`supabase` or `local`) | `local` | Yes |
| `MAX_USERS` | Maximum number of users allowed | `100` | Yes |
| `ENABLE_USER_REGISTRATION` | Allow public signups (`1` or `0`) | `0` | Yes |
| `RATE_LIMIT_REQUESTS` | Rate limit requests per minute | `60` | Yes |
| `RATE_LIMIT_BURST` | Rate limit burst capacity | `10` | Yes |
| `LOG_LEVEL` | Logging level | `WARNING` | Yes |
| `PRODUCTION` | Production mode flag | `1` | Yes |
| `SYSTEM_APPS_REPO` | Git URL for system apps | Default repo | Yes |

### Render Configuration (`render.yaml`)

```yaml
services:
  - type: web
    name: tronbyt-server
    runtime: docker
    dockerfilePath: ./Dockerfile
    plan: starter
    healthCheckPath: /health
    envVars:
      - key: SUPABASE_URL
        sync: false
      - key: SUPABASE_ANON_KEY
        sync: false
      - key: SUPABASE_SERVICE_ROLE_KEY
        sync: false
      - key: SECRET_KEY
        generateValue: true
      - key: AUTH_MODE
        value: supabase
      - key: PRODUCTION
        value: "1"
      - key: LOG_LEVEL
        value: WARNING
    disk:
      name: tronbyt-data
      mountPath: /app/data
      sizeGB: 1
```

---

## File-by-File Guide

### Files to Create

| File | Purpose |
|------|---------|
| `tronbyt_server/supabase_client.py` | Supabase client initialization |
| `tronbyt_server/supabase_auth.py` | Auth middleware for Supabase |
| `tronbyt_server/supabase_db.py` | Database operations using Supabase |
| `tronbyt_server/device_claim.py` | Device pairing/claiming logic |
| `tronbyt_server/rate_limit.py` | Rate limiting middleware |

### Files to Modify

| File | Changes Required |
|------|------------------|
| `tronbyt_server/config.py` | Add Supabase environment variables |
| `tronbyt_server/main.py` | Add rate limiting middleware, conditional auth |
| `tronbyt_server/dependencies.py` | Add Supabase auth dependency |
| `tronbyt_server/routers/auth.py` | Redirect to Supabase Auth for login/signup |
| `tronbyt_server/routers/api.py` | Use Supabase auth for API routes |
| `tronbyt_server/routers/manager.py` | Use Supabase auth for manager routes |
| `pyproject.toml` | Add new dependencies |

### Files That Stay the Same

- `tronbyt_server/pixlet.py` - Rendering logic unchanged
- `tronbyt_server/firmware_utils.py` - Firmware generation unchanged
- `tronbyt_server/templates/*` - Templates mostly unchanged
- `tronbyt_server/static/*` - Static files unchanged

---

## Code Examples

The following code files implement the Supabase integration. See the corresponding files in `tronbyt_server/` for the complete implementation:

- `tronbyt_server/supabase_client.py` - Supabase client initialization
- `tronbyt_server/supabase_auth.py` - Authentication middleware
- `tronbyt_server/device_claim.py` - Device claiming logic
- `tronbyt_server/rate_limit.py` - Rate limiting

---

## Deployment Checklist

### Pre-Deployment

- [ ] Create Supabase project at https://supabase.com
- [ ] Run schema SQL in Supabase SQL Editor
- [ ] Run RLS policies SQL in Supabase SQL Editor
- [ ] Run triggers SQL in Supabase SQL Editor
- [ ] Note down Supabase URL from Project Settings > API
- [ ] Note down `anon` public key from Project Settings > API
- [ ] Note down `service_role` key from Project Settings > API
- [ ] Enable Email Auth in Authentication > Providers

### Render Setup

- [ ] Create new Web Service on Render
- [ ] Connect to GitHub repository
- [ ] Set Docker as runtime
- [ ] Configure environment variables:
  - `SUPABASE_URL`
  - `SUPABASE_ANON_KEY`
  - `SUPABASE_SERVICE_ROLE_KEY`
  - `SECRET_KEY` (generate unique value)
  - `AUTH_MODE=supabase`
  - `PRODUCTION=1`
- [ ] Attach persistent disk (1GB minimum) at `/app/data`
- [ ] Deploy and verify health check passes

### Post-Deployment Verification

- [ ] Visit web UI and test signup flow
- [ ] Verify email confirmation works
- [ ] Test login/logout
- [ ] Create a test device
- [ ] Verify device shows in dashboard
- [ ] Test API with generated API key
- [ ] Verify rate limiting works
- [ ] Check Supabase logs for any errors

### Security Verification

- [ ] Confirm RLS is enabled on all tables
- [ ] Test that users cannot access other users' data
- [ ] Verify API keys are unique per user
- [ ] Test rate limiting on public endpoints
- [ ] Confirm no admin bypass routes exist
- [ ] Verify HTTPS is enforced

---

## Additional Notes

### Migrating Existing Data

If you have existing SQLite data to migrate, you'll need to:

1. Export users from SQLite JSON format
2. Create Supabase Auth accounts for each user
3. Import user profiles with matching IDs
4. Transform device/app JSON blobs to normalized tables

A migration script would be needed for this process.

### Image Storage

For WebP image storage, you have two options:

1. **Render Disk (Recommended for simplicity)**: Continue using local disk at `/app/data`
2. **Supabase Storage**: Store images in Supabase buckets for better scalability

The current implementation assumes Render Disk for image storage.

### Firmware Integration

The firmware needs to be updated to:

1. Generate unique device IDs
2. Call the pairing token endpoint during setup
3. Display the pairing token/QR code to the user

This is outside the scope of the server changes.
