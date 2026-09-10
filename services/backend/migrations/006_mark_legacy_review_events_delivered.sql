update report_review_events
set delivery_status = 'submitted',
    delivered_at = coalesce(delivered_at, created_at),
    delivery_updated_at = now()
where delivery_status = 'pending'
  and delivery_attempts = 0;
