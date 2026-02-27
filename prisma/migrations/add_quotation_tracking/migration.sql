-- Migration: Add Client Quotation Portal Tracking Fields
-- Description: Adds fields to Quotation for client portal tracking and Project for quotation origin
-- Date: 2026-02-06

-- Add portal tracking fields to Quotation table
ALTER TABLE "Quotation" ADD COLUMN IF NOT EXISTS "verified_at" TIMESTAMP(3);
ALTER TABLE "Quotation" ADD COLUMN IF NOT EXISTS "client_viewed_at" TIMESTAMP(3);
ALTER TABLE "Quotation" ADD COLUMN IF NOT EXISTS "client_response_at" TIMESTAMP(3);
ALTER TABLE "Quotation" ADD COLUMN IF NOT EXISTS "client_response_note" TEXT;
ALTER TABLE "Quotation" ADD COLUMN IF NOT EXISTS "expires_at" TIMESTAMP(3);
ALTER TABLE "Quotation" ADD COLUMN IF NOT EXISTS "created_from_portal" BOOLEAN DEFAULT false NOT NULL;

-- Add quotation origin tracking to Project table
ALTER TABLE "Project" ADD COLUMN IF NOT EXISTS "created_from_quotation" BOOLEAN DEFAULT false NOT NULL;
ALTER TABLE "Project" ADD COLUMN IF NOT EXISTS "contact" TEXT;
ALTER TABLE "Project" ADD COLUMN IF NOT EXISTS "email" TEXT;
