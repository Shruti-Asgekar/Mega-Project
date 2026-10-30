/**
 * Database seeder — creates 6 demo user accounts (one per role).
 * Safe to run multiple times (upsert).
 */
import { PrismaClient } from '@prisma/client';
import bcrypt from 'bcryptjs';

const prisma = new PrismaClient();

const DEMO_PASSWORD = 'Demo@1234';
const demoUsers = [
  { name: 'Aarav Mehta (Demo Applicant)', email: 'applicant@kyc.local', role: 'APPLICANT' },
  { name: 'Priya Sharma (Demo Officer)', email: 'officer@kyc.local', role: 'OFFICER' },
  { name: 'Vikram Nair (Demo Manager)', email: 'manager@kyc.local', role: 'MANAGER' },
  { name: 'Shreya Iyer (Demo Fraud Analyst)', email: 'fraud@kyc.local', role: 'FRAUD_ANALYST' },
  { name: 'Rohan Verma (Demo Auditor)', email: 'auditor@kyc.local', role: 'AUDITOR' },
  { name: 'Admin User', email: 'admin@kyc.local', role: 'ADMIN' },
];

async function main() {
  console.log('Seeding demo user accounts...');
  const hash = await bcrypt.hash(DEMO_PASSWORD, 12);

  for (const u of demoUsers) {
    await prisma.user.upsert({
      where: { email: u.email },
      update: { name: u.name, role: u.role as any, passwordHash: hash, isActive: true },
      create: { name: u.name, email: u.email, passwordHash: hash, role: u.role as any, isActive: true },
    });
    console.log(`  ✓ ${u.role}: ${u.email}`);
  }
  console.log('Seeding complete.');
}

main()
  .catch(e => { console.error(e); process.exit(1); })
  .finally(() => prisma.$disconnect());
