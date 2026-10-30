import 'dotenv/config';
import express from 'express';
import cookieParser from 'cookie-parser';
import cors from 'cors';
import helmet from 'helmet';
import { config } from './config';
import { errorHandler } from './middleware/errorHandler';
import { apiLimiter } from './middleware/rateLimiter';

import authRoutes from './routes/auth.routes';
import applicationRoutes from './routes/application.routes';
import documentRoutes from './routes/document.routes';
import decisionRoutes from './routes/decision.routes';
import auditRoutes from './routes/audit.routes';
import adminRoutes from './routes/admin.routes';
import ledgerRoutes from './routes/ledger.routes';
import analyticsRoutes from './routes/analytics.routes';

const app = express();

app.use(helmet());
app.use(cors({ origin: config.frontendUrl, credentials: true }));
app.use(cookieParser());
app.use(express.json({ limit: '5mb' }));
app.use(express.urlencoded({ extended: true }));
app.use('/api', apiLimiter);

// Health check
app.get('/api/health', (_req, res) => {
  res.json({ status: 'healthy', service: 'backend', timestamp: new Date().toISOString() });
});

// Routes
app.use('/api/auth', authRoutes);
app.use('/api/applications', applicationRoutes);
app.use('/api/documents', documentRoutes);
app.use('/api/decisions', decisionRoutes);
app.use('/api/audit', auditRoutes);
app.use('/api/admin', adminRoutes);
app.use('/api/ledger', ledgerRoutes);
app.use('/api/analytics', analyticsRoutes);

app.use(errorHandler);

if (process.env.NODE_ENV !== 'test') {
  app.listen(config.port, () => {
    console.log(`[Backend] Server running on port ${config.port} in ${config.nodeEnv} mode`);
  });
}

export default app;
