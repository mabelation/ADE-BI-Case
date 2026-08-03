from src.ingestion.eurolam import save_eurolam_staging
from src.ingestion.indabel import save_indabel_staging
from src.ingestion.turio import save_turio_staging
from src.transformations.canonical_sales import build_canonical_sales
from src.reporting.control_figures import save_control_outputs
from src.forecasting.forecasting import build_forecast
from src.churn.churn import build_churn_risk
from src.profitability.profitability import run_profitability_analysis
from src.forecasting.forecast_v2 import build_forecast_v2
from src.churn.churn_v2 import build_customer_health_index
from src.forecasting.forecast_v3 import build_forecast_v3_scenarios
from src.churn.churn_v3 import build_customer_recovery_priority


def main() -> None:
    print("ADE Group — Pipeline de BI y Analítica")
    print("=" * 45)

    save_eurolam_staging()
    print()

    save_indabel_staging()
    print()

    save_turio_staging()
    print()

    build_canonical_sales()
    print()

    save_control_outputs()
    print()

    build_forecast()
    print()

    build_churn_risk()
    print()
    
    run_profitability_analysis()
    print()

    build_forecast_v2()
    print()

    build_customer_health_index()
    print()

    build_forecast_v3_scenarios()
    print()
    
    build_customer_recovery_priority()

if __name__ == "__main__":
    main()