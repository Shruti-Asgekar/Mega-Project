/**
 * RBAC & Maker-Checker Tests for backend routes.
 * Uses supertest against the Express app with a test SQLite database.
 * Database is mocked via jest to avoid requiring a real Postgres.
 */
import request from 'supertest';
import app from '../src/server';
import jwt from 'jsonwebtoken';
import { config } from '../src/config';

function makeToken(userId: string, role: string, email = `${role.toLowerCase()}@test.com`): string {
  return jwt.sign({ userId, email, role }, config.jwtSecret, { expiresIn: '1h' });
}

// Mock prisma so tests don't need a real database
jest.mock('../src/db', () => ({
  prisma: {
    user: {
      findUnique: jest.fn(),
      findMany: jest.fn().mockResolvedValue([]),
      create: jest.fn(),
      update: jest.fn(),
    },
    auditLog: {
      create: jest.fn().mockResolvedValue({}),
      findMany: jest.fn().mockResolvedValue([]),
      count: jest.fn().mockResolvedValue(0),
    },
    application: {
      findUnique: jest.fn(),
      findMany: jest.fn().mockResolvedValue([]),
      create: jest.fn(),
      update: jest.fn(),
      count: jest.fn().mockResolvedValue(0),
      groupBy: jest.fn().mockResolvedValue([]),
    },
    document: {
      findUnique: jest.fn(),
      create: jest.fn(),
    },
    decision: {
      create: jest.fn(),
      findFirst: jest.fn(),
    },
    processingJob: {
      create: jest.fn(),
      findFirst: jest.fn().mockResolvedValue(null),
    },
    consentRecord: {
      create: jest.fn(),
    },
    ledgerEntry: {
      findUnique: jest.fn().mockResolvedValue(null),
    },
    finding: {
      groupBy: jest.fn().mockResolvedValue([]),
    },
  },
}));

describe('API Health Check', () => {
  test('GET /api/health returns healthy', async () => {
    const res = await request(app).get('/api/health');
    expect(res.status).toBe(200);
    expect(res.body.status).toBe('healthy');
  });
});

describe('Auth: Unauthenticated requests', () => {
  test('GET /api/auth/me without token returns 401', async () => {
    const res = await request(app).get('/api/auth/me');
    expect(res.status).toBe(401);
    expect(res.body.code).toBe('NO_TOKEN');
  });

  test('GET /api/audit/logs without token returns 401', async () => {
    const res = await request(app).get('/api/audit/logs');
    expect(res.status).toBe(401);
  });
});

describe('RBAC: Role enforcement', () => {
  test('APPLICANT cannot access audit logs (403)', async () => {
    const token = makeToken('user-1', 'APPLICANT');
    const res = await request(app)
      .get('/api/audit/logs')
      .set('Authorization', `Bearer ${token}`);
    expect(res.status).toBe(403);
    expect(res.body.code).toBe('FORBIDDEN');
  });

  test('AUDITOR can access audit logs (200)', async () => {
    const token = makeToken('user-2', 'AUDITOR');
    const res = await request(app)
      .get('/api/audit/logs')
      .set('Authorization', `Bearer ${token}`);
    expect(res.status).toBe(200);
  });

  test('APPLICANT cannot access admin users (403)', async () => {
    const token = makeToken('user-1', 'APPLICANT');
    const res = await request(app)
      .get('/api/admin/users')
      .set('Authorization', `Bearer ${token}`);
    expect(res.status).toBe(403);
  });

  test('ADMIN can access admin users (200)', async () => {
    const token = makeToken('user-3', 'ADMIN');
    const res = await request(app)
      .get('/api/admin/users')
      .set('Authorization', `Bearer ${token}`);
    expect(res.status).toBe(200);
  });

  test('OFFICER cannot access final decision endpoint (403)', async () => {
    const token = makeToken('officer-1', 'OFFICER');
    const res = await request(app)
      .post('/api/decisions/final')
      .set('Authorization', `Bearer ${token}`)
      .send({ applicationId: 'app-1', outcome: 'APPROVED', reason: 'test' });
    expect(res.status).toBe(403);
    expect(res.body.code).toBe('FORBIDDEN');
  });
});

describe('Maker-Checker: Same user cannot recommend AND approve', () => {
  const { prisma } = require('../src/db');

  test('MANAGER who recommended is blocked from final approval', async () => {
    const token = makeToken('mgr-1', 'MANAGER');
    // Simulate: this manager has a prior recommendation on this application
    prisma.decision.findFirst.mockResolvedValueOnce({
      id: 'dec-1', userId: 'mgr-1', kind: 'RECOMMENDATION',
    });
    const res = await request(app)
      .post('/api/decisions/final')
      .set('Authorization', `Bearer ${token}`)
      .send({ applicationId: 'app-x', outcome: 'APPROVED', reason: 'looks good' });
    expect(res.status).toBe(403);
    expect(res.body.code).toBe('MAKER_CHECKER_VIOLATION');
  });

  test('Different MANAGER can give final approval (201)', async () => {
    const token = makeToken('mgr-2', 'MANAGER');
    // No prior recommendation by mgr-2
    prisma.decision.findFirst.mockResolvedValueOnce(null);
    prisma.application.findUnique.mockResolvedValueOnce({ id: 'app-y', status: 'RECOMMENDED' });
    prisma.decision.create.mockResolvedValueOnce({ id: 'dec-2', kind: 'FINAL', outcome: 'APPROVED' });
    prisma.application.update.mockResolvedValueOnce({ id: 'app-y', status: 'APPROVED' });
    const res = await request(app)
      .post('/api/decisions/final')
      .set('Authorization', `Bearer ${token}`)
      .send({ applicationId: 'app-y', outcome: 'APPROVED', reason: 'approved' });
    expect(res.status).toBe(201);
  });
});

describe('PII Masking: maskAadhaar and maskPan', () => {
  const { maskAadhaar, maskPan } = require('../src/utils/contracts');

  test('maskAadhaar hides first 8 digits', () => {
    expect(maskAadhaar('498174981234')).toBe('XXXX-XXXX-1234');
    expect(maskAadhaar('1234 5678 9012')).toBe('XXXX-XXXX-9012');
  });

  test('maskAadhaar handles invalid input', () => {
    expect(maskAadhaar('short')).toBe('XXXX-XXXX-XXXX');
  });

  test('maskPan hides middle characters', () => {
    expect(maskPan('ABCDE1234F')).toBe('ABCXX1234F');
  });
});

describe('Consent: Application requires consent', () => {
  test('POST /api/applications without consentText returns 400', async () => {
    const token = makeToken('app-1', 'APPLICANT');
    const res = await request(app)
      .post('/api/applications')
      .set('Authorization', `Bearer ${token}`)
      .send({});
    expect(res.status).toBe(400);
    expect(res.body.code).toBe('CONSENT_REQUIRED');
  });
});
