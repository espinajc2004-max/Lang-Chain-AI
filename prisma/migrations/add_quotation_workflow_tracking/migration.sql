-- Migration: Add Quotation Workflow Tracking Fields
-- Description: Adds fields to track quotation-request relationships and rejection history
-- Date: 2026-02-04

-- Add fields to quotation_request table
ALTER TABLE quotation_request 
ADD COLUMN IF NOT EXISTS active_quotation_id TEXT,
ADD COLUMN IF NOT EXISTS rejection_count INTEGER DEFAULT 0 NOT NULL,
ADD COLUMN IF NOT EXISTS last_rejected_at TIMESTAMP(3);

-- Add rejection_reason field to Quotation table
ALTER TABLE "Quotation"
ADD COLUMN IF NOT EXISTS rejection_reason TEXT;

-- Add foreign key constraint to link request to quotation
ALTER TABLE quotation_request
ADD CONSTRAINT fk_quotation_request_active_quotation 
FOREIGN KEY (active_quotation_id) 
REFERENCES "Quotation"(id) 
ON DELETE SET NULL
ON UPDATE CASCADE;

-- Add index for performance on active_quotation_id lookups
CREATE INDEX IF NOT EXISTS quotation_request_active_quotation_id_idx 
ON quotation_request(active_quotation_id);

-- Add comments for documentation
COMMENT ON COLUMN quotation_request.active_quotation_id IS 'Links to the currently active quotation (PENDING or APPROVED status). NULL if no active quotation or if rejected.';
COMMENT ON COLUMN quotation_request.rejection_count IS 'Number of times quotations for this request have been rejected by accountant or admin';
COMMENT ON COLUMN quotation_request.last_rejected_at IS 'Timestamp of the most recent quotation rejection';
COMMENT ON COLUMN "Quotation".rejection_reason IS 'Reason provided when quotation is rejected by accountant or admin';
