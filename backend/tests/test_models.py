from datetime import date

from app.models.loan import Loan, LoanSummary
from app.models.package import PackageSummary, Package
from app.models.simulation import SimulationConfig
from app.models.valuation import MonthlyCashFlow, LoanValuationResult


def test_loan_full():
    loan = Loan(
        loan_id="L001",
        unpaid_balance=250000.0,
        interest_rate=0.045,
        original_term=360,
        remaining_term=340,
        loan_age=20,
        credit_score=740,
        ltv=0.75,
        dti=0.35,
        property_type="SFR",
        occupancy_type="Owner",
        state="CA",
        origination_date=date(2024, 6, 15),
    )
    assert loan.loan_id == "L001"
    assert loan.unpaid_balance == 250000.0


def test_loan_minimal():
    loan = Loan(
        loan_id="L002",
        unpaid_balance=100000.0,
        interest_rate=0.05,
        original_term=360,
        remaining_term=360,
        loan_age=0,
    )
    assert loan.credit_score is None
    assert loan.state is None


def test_loan_summary():
    summary = LoanSummary(
        loan_id="L001",
        unpaid_balance=250000.0,
        interest_rate=0.045,
    )
    assert summary.loan_id == "L001"


def test_package_summary():
    pkg = PackageSummary(
        package_id="PKG-001",
        name="Test Package",
        loan_count=50,
        total_upb=12500000.0,
    )
    assert pkg.purchase_price is None
    assert pkg.loan_count == 50


def test_package_with_loans():
    loan = Loan(
        loan_id="L001",
        unpaid_balance=250000.0,
        interest_rate=0.045,
        original_term=360,
        remaining_term=340,
        loan_age=20,
    )
    pkg = Package(
        package_id="PKG-001",
        name="Test Package",
        loan_count=1,
        total_upb=250000.0,
        loans=[loan],
    )
    assert len(pkg.loans) == 1
    assert pkg.loans[0].loan_id == "L001"


def test_simulation_config_defaults():
    config = SimulationConfig()
    assert config.n_simulations == 500
    assert "baseline" in config.scenarios
    assert config.stochastic_seed == 42


def test_monthly_cash_flow():
    cf = MonthlyCashFlow(
        month=1,
        scheduled_payment=1200.0,
        survival_probability=0.99,
        expected_payment=1188.0,
        deq_probability=0.01,
        default_probability=0.001,
        expected_loss=25.0,
        expected_recovery=0.0,
        prepay_probability=0.005,
        expected_prepayment=1000.0,
        servicing_cost=25.0,
        net_cash_flow=2138.0,
        discount_factor=0.9934,
        present_value=2123.89,
    )
    assert cf.month == 1
    assert cf.present_value == 2123.89
    assert cf.prepay_probability == 0.005
    assert cf.expected_prepayment == 1000.0


def test_loan_valuation_result():
    result = LoanValuationResult(
        loan_id="L001",
        bucket_id=2,
        expected_pv=240000.0,
        pv_by_scenario={"baseline": 245000.0, "mild_recession": 230000.0},
        pv_distribution=[240000.0, 241000.0, 239000.0],
        pv_percentiles={"p5": 220000.0, "p50": 240000.0, "p95": 260000.0},
        monthly_cash_flows=[],
        model_status={"survival": "stub", "deq": "stub"},
    )
    assert result.bucket_id == 2
    assert result.pv_by_scenario["baseline"] == 245000.0
