-- LOCAL TEST SCRIPT ONLY — exercises the RLS policies from
-- 41619a38de4a_rls_policies.py against real Postgres role-switching, the
-- same mechanism PostgREST/Supabase uses in production (SET ROLE
-- authenticated + a request.jwt.claims GUC carrying the verified `sub`).
--
-- Every \echo marks a scenario; every scenario ends by asserting row counts
-- with a RAISE EXCEPTION if the result doesn't match what tenant isolation
-- requires, so a failure aborts the script loudly rather than being missed
-- in scrollback.

\set ON_ERROR_STOP on

BEGIN;

-- --- Fixture: two tenants, one profile each, a super admin, and one row
-- of tenant-owned data (a customer) per tenant. No fake business data is
-- left behind — this whole block runs inside a transaction that gets
-- rolled back at the end of the script.
INSERT INTO auth.users (id, email) VALUES
  ('11111111-1111-1111-1111-111111111111', 'owner-a@tenant-a.test'),
  ('22222222-2222-2222-2222-222222222222', 'owner-b@tenant-b.test'),
  ('33333333-3333-3333-3333-333333333333', 'root@platform.test');

INSERT INTO public.tenants (id, name, slug) VALUES
  ('aaaaaaaa-0000-0000-0000-000000000000', 'Tenant A', 'tenant-a'),
  ('bbbbbbbb-0000-0000-0000-000000000000', 'Tenant B', 'tenant-b');

UPDATE public.profiles SET tenant_id = 'aaaaaaaa-0000-0000-0000-000000000000'
  WHERE id = '11111111-1111-1111-1111-111111111111';
UPDATE public.profiles SET tenant_id = 'bbbbbbbb-0000-0000-0000-000000000000'
  WHERE id = '22222222-2222-2222-2222-222222222222';
-- root@platform.test stays tenant_id = NULL (platform-wide).

INSERT INTO public.profile_roles (profile_id, role_id, tenant_id)
SELECT '11111111-1111-1111-1111-111111111111', id, 'aaaaaaaa-0000-0000-0000-000000000000'
FROM public.roles WHERE code = 'TENANT_OWNER';
INSERT INTO public.profile_roles (profile_id, role_id, tenant_id)
SELECT '22222222-2222-2222-2222-222222222222', id, 'bbbbbbbb-0000-0000-0000-000000000000'
FROM public.roles WHERE code = 'TENANT_OWNER';
INSERT INTO public.profile_roles (profile_id, role_id, tenant_id)
SELECT '33333333-3333-3333-3333-333333333333', id, NULL
FROM public.roles WHERE code = 'SUPER_ADMIN';

INSERT INTO public.customers (id, tenant_id, phone, first_name, customer_number) VALUES
  ('c0000000-0000-0000-0000-00000000000a', 'aaaaaaaa-0000-0000-0000-000000000000', '+255700000001', 'Customer A1', 'CUS000001'),
  ('c0000000-0000-0000-0000-00000000000b', 'bbbbbbbb-0000-0000-0000-000000000000', '+255700000002', 'Customer B1', 'CUS000001');

\echo '--- Scenario 1: Tenant A owner sees only Tenant A customers ---'
SET LOCAL ROLE authenticated;
SET LOCAL request.jwt.claims = '{"sub": "11111111-1111-1111-1111-111111111111"}';

DO $$
DECLARE visible_count int;
BEGIN
  SELECT count(*) INTO visible_count FROM public.customers;
  IF visible_count != 1 THEN
    RAISE EXCEPTION 'FAIL: tenant A owner should see exactly 1 customer, saw %', visible_count;
  END IF;
  RAISE NOTICE 'PASS: tenant A owner sees exactly their own 1 customer';
END $$;

DO $$
DECLARE leaked_count int;
BEGIN
  SELECT count(*) INTO leaked_count FROM public.customers WHERE tenant_id = 'bbbbbbbb-0000-0000-0000-000000000000';
  IF leaked_count != 0 THEN
    RAISE EXCEPTION 'FAIL: tenant A owner should see 0 rows of tenant B, saw %', leaked_count;
  END IF;
  RAISE NOTICE 'PASS: tenant A owner sees 0 rows belonging to tenant B (no cross-tenant leak)';
END $$;

RESET ROLE;

\echo '--- Scenario 2: Tenant A owner cannot INSERT a row tagged as Tenant B ---'
SET LOCAL ROLE authenticated;
SET LOCAL request.jwt.claims = '{"sub": "11111111-1111-1111-1111-111111111111"}';

DO $$
BEGIN
  BEGIN
    INSERT INTO public.customers (tenant_id, phone, first_name, customer_number)
    VALUES ('bbbbbbbb-0000-0000-0000-000000000000', '+255700000099', 'Cross-tenant injection attempt', 'CUS999999');
    RAISE EXCEPTION 'FAIL: cross-tenant INSERT should have been rejected by RLS but succeeded';
  EXCEPTION
    WHEN insufficient_privilege OR check_violation THEN
      RAISE NOTICE 'PASS: cross-tenant INSERT correctly denied by RLS (%)', SQLERRM;
  END;
END $$;

RESET ROLE;

\echo '--- Scenario 3: Tenant A owner cannot UPDATE a Tenant B row (even by primary key) ---'
SET LOCAL ROLE authenticated;
SET LOCAL request.jwt.claims = '{"sub": "11111111-1111-1111-1111-111111111111"}';

DO $$
DECLARE affected int;
BEGIN
  UPDATE public.customers SET first_name = 'Hijacked' WHERE id = 'c0000000-0000-0000-0000-00000000000b';
  GET DIAGNOSTICS affected = ROW_COUNT;
  IF affected != 0 THEN
    RAISE EXCEPTION 'FAIL: tenant A owner updated % row(s) belonging to tenant B', affected;
  END IF;
  RAISE NOTICE 'PASS: cross-tenant UPDATE affected 0 rows (RLS USING clause hid the row)';
END $$;

RESET ROLE;

\echo '--- Scenario 4: an authenticated user with no profile sees nothing (fail closed) ---'
SET LOCAL ROLE authenticated;
SET LOCAL request.jwt.claims = '{"sub": "99999999-9999-9999-9999-999999999999"}';

DO $$
DECLARE visible_count int;
BEGIN
  SELECT count(*) INTO visible_count FROM public.customers;
  IF visible_count != 0 THEN
    RAISE EXCEPTION 'FAIL: a profile-less user should see 0 customers, saw %', visible_count;
  END IF;
  RAISE NOTICE 'PASS: profile-less/unrecognized user sees 0 rows (fails closed, not open)';
END $$;

RESET ROLE;

\echo '--- Scenario 5: super admin sees across both tenants ---'
SET LOCAL ROLE authenticated;
SET LOCAL request.jwt.claims = '{"sub": "33333333-3333-3333-3333-333333333333"}';

DO $$
DECLARE visible_count int;
BEGIN
  SELECT count(*) INTO visible_count FROM public.customers;
  IF visible_count != 2 THEN
    RAISE EXCEPTION 'FAIL: super admin should see both tenants'' customers (2), saw %', visible_count;
  END IF;
  RAISE NOTICE 'PASS: super admin sees all % customers across tenants', visible_count;
END $$;

RESET ROLE;

\echo '--- Scenario 6: anon (unauthenticated) role sees nothing ---'
SET LOCAL ROLE anon;
SET LOCAL request.jwt.claims = '{}';

DO $$
DECLARE visible_count int;
BEGIN
  SELECT count(*) INTO visible_count FROM public.customers;
  IF visible_count != 0 THEN
    RAISE EXCEPTION 'FAIL: anon should see 0 customers (no policy grants it access), saw %', visible_count;
  END IF;
  RAISE NOTICE 'PASS: anon role sees 0 rows (no RLS policy targets anon on this table)';
END $$;

RESET ROLE;

\echo '--- Scenario 7: reference tables (roles) are readable by any authenticated user ---'
SET LOCAL ROLE authenticated;
SET LOCAL request.jwt.claims = '{"sub": "11111111-1111-1111-1111-111111111111"}';

DO $$
DECLARE role_count int;
BEGIN
  SELECT count(*) INTO role_count FROM public.roles;
  IF role_count != 8 THEN
    RAISE EXCEPTION 'FAIL: expected 8 seeded roles visible, saw %', role_count;
  END IF;
  RAISE NOTICE 'PASS: reference table (roles) readable, sees all % rows', role_count;
END $$;

DO $$
BEGIN
  BEGIN
    INSERT INTO public.roles (code, name) VALUES ('HACKED', 'Should not be allowed');
    RAISE EXCEPTION 'FAIL: authenticated role should not be able to write to public.roles';
  EXCEPTION
    WHEN insufficient_privilege THEN
      RAISE NOTICE 'PASS: authenticated role cannot write to the immutable roles catalog (%)', SQLERRM;
  END;
END $$;

RESET ROLE;

\echo '--- Scenario 8: audit_logs is read-only to tenant clients (no write policy) ---'
SET LOCAL ROLE authenticated;
SET LOCAL request.jwt.claims = '{"sub": "11111111-1111-1111-1111-111111111111"}';

DO $$
BEGIN
  BEGIN
    INSERT INTO public.audit_logs (tenant_id, action) VALUES ('aaaaaaaa-0000-0000-0000-000000000000', 'tampered');
    RAISE EXCEPTION 'FAIL: authenticated role should not be able to write audit_logs directly';
  EXCEPTION
    WHEN insufficient_privilege THEN
      RAISE NOTICE 'PASS: audit_logs has no INSERT policy for authenticated (backend-only writes) (%)', SQLERRM;
  END;
END $$;

RESET ROLE;

\echo 'ALL SCENARIOS PASSED'

ROLLBACK;
