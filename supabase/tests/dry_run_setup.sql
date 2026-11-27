-- Disposable CI database only.
create role anon;
create role service_role;
create role authenticated;
create schema auth;
create table auth.users(id uuid primary key, created_at timestamptz default now());
insert into auth.users values ('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa');
create function auth.uid() returns uuid language sql as $$select null::uuid$$;
create function auth.jwt() returns jsonb language sql as $$select '{}'::jsonb$$;
create schema extensions;
create extension pgcrypto with schema extensions;
