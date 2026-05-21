# DAG Workflow (Current Project)

End-to-end workflow from raw CSV to ML artifacts.

```
deliveries.csv
  → ingest_data.py (COPY into PostgreSQL)
  → public.raw_deliveries
  → dbt: staging → core → marts
  → dbt_schema_marts.ml_training_dataset
  → ml_models_enhanced.py
  → models/eta_pipeline.joblib
  → models/feature_contract.joblib
  → models/feature_metadata.joblib
```

## Key dbt models (current)

- `stg_orders` (staging view)
- `dim_driver` (core table)
- `dim_restaurant` (core table)
- `fact_orders` (core table, includes validation flags)
- `fct_orders` (marts table, clean rows only)
- `ml_training_dataset` (marts view used by ML training)

## ML artifacts

- `eta_pipeline.joblib` (preprocessor + XGBoost)
- `feature_contract.joblib` (frozen schema snapshot)
- `feature_metadata.joblib` (params + metrics + row counts)

---

## Error Handling

### Retry Logic

Each task has:
- **Retries**: 2 attempts
- **Retry Delay**: 5 minutes
- **Timeout**: 2 hours (pipeline level)

### Failure Scenarios

**Scenario 1: Data Ingestion Fails**
```
ingest_raw_data ❌ → Retry (5 min) → Retry (5 min) → Email Alert
```
- Pipeline stops
- No downstream tasks run
- Manual intervention required

**Scenario 2: dbt Test Fails**
```
dbt_test ❌ → Retry → Retry → Email Alert
```
- ML training doesn't run
- Previous day's models remain active
- Data quality issue flagged

**Scenario 3: Model Training Fails**
```
train_ml_models ❌ → Retry → Retry → Email Alert
```
- Predictions use previous day's models
- Quality check may flag stale models
- Investigation required

---

## Monitoring Metrics

### Success Metrics
- ✅ Pipeline Success Rate: > 95%
- ✅ Average Duration: 30-35 minutes
- ✅ Model Accuracy: > 90% R²
- ✅ Data Quality: 100% checks passing

### Alert Thresholds
- 🚨 Pipeline Duration > 60 minutes
- 🚨 Task Failure Rate > 5%
- 🚨 Model Accuracy < 85%
- 🚨 Data Quality Checks Failing

---

## Dependencies

### External Dependencies
- PostgreSQL database (running)
- Python virtual environment (activated)
- dbt profiles configured
- Sufficient disk space (> 5GB)
- Network connectivity (for API calls)

### Internal Dependencies
```
ingest_data.py
ml_models_enhanced.py
save_models_for_streamlit.py
generate_daily_predictions.py
data_quality_check.py
```

---

## Maintenance Windows

### Recommended Schedule
- **Daily Run**: 2:00 AM (low traffic)
- **Maintenance**: Sunday 3:00 AM
- **Model Retraining**: Daily
- **Full Refresh**: Weekly (Sunday)

### Downtime Impact
- **During Pipeline**: Predictions use cached models
- **Streamlit App**: Continues with previous models
- **User Impact**: Minimal (off-peak hours)

---

## Performance Optimization

### Current Performance
- Total Duration: ~31 minutes
- Bottleneck: Model training (10-20 min)
- Parallelization: Limited (sequential tasks)

### Optimization Opportunities
1. **Parallel dbt runs**: Run staging models in parallel
2. **Incremental models**: Only process new data
3. **Model caching**: Skip training if data unchanged
4. **Resource allocation**: Increase compute for ML tasks

---

## Disaster Recovery

### Backup Strategy
- **Database**: Daily backups at 1:00 AM
- **Models**: Versioned in model registry
- **Code**: Git version control
- **Logs**: Retained for 30 days

### Recovery Procedures
1. **Pipeline Failure**: Retry from failed task
2. **Data Corruption**: Restore from backup
3. **Model Degradation**: Rollback to previous version
4. **Complete Failure**: Full pipeline re-run

---

## Future Enhancements

### Planned Improvements
1. **Parallel Execution**: Run independent tasks concurrently
2. **Dynamic Scheduling**: Adjust based on data volume
3. **Advanced Monitoring**: Real-time dashboards
4. **Auto-scaling**: Resource allocation based on load
5. **A/B Testing**: Compare model versions
6. **Feature Store**: Centralized feature management

---

**📊 This workflow ensures your Delivery DSS stays fresh with daily updates!**

*Last Updated: 2024*
