SET QUOTED_IDENTIFIER, ANSI_NULLS ON
GO
CREATE    VIEW [bid].[LoanTotalOperatingCosts] AS 
-- Getting the accounts separately
WITH meProfitData AS (
SELECT 
    a.account_number,
    SUM(CASE WHEN a.data_point_id = 80 THEN a.data_value ELSE 0 END) AS cost_to_acquire,
    SUM(CASE WHEN a.data_point_id = 180 THEN a.data_value ELSE 0 END) AS non_inventory,
    SUM(CASE WHEN a.data_point_id = 100 THEN a.data_value ELSE 0 END) AS customer_service,
    SUM(CASE WHEN a.data_point_id IN (110, 130) THEN a.data_value ELSE 0 END) AS coll_fore,
    SUM(CASE WHEN a.data_point_id = 120 THEN a.data_value ELSE 0 END) AS bankruptcy
FROM reporting.fnba.me_profit_data a
GROUP BY a.account_number
),

-- Getting the months active and avg investment
monthsActive AS (
SELECT 
    a.account_number, 
    SUM(x.fractionOfMonthOnBooks) AS months_active,
    AVG(x.averageInvestment) AS avgInvestment
FROM meProfitData AS a
JOIN relmeom.profit.investmentAndCapital x 
    ON x.accountNumber = a.account_number
GROUP BY a.account_number
)

-- Getting the annualization
SELECT 
    a.account_number,
    IIF(b.months_active < 12, 12, b.months_active) AS months_active,
    a.cost_to_acquire,
    a.cost_to_acquire / 48 * 12 AS cost_to_acquire_a,
    a.non_inventory,
    a.non_inventory / 48 * 12 AS non_inventory_a,
    a.customer_service,
    a.customer_service / IIF(b.months_active < 12, 12, b.months_active) * 12 AS customer_service_a,
    a.coll_fore,
    a.coll_fore / IIF(b.months_active < 12, 12, b.months_active) * 12 AS coll_fore_a,
    a.bankruptcy,
    a.bankruptcy / IIF(b.months_active < 12, 12, b.months_active) * 12 AS bankruptcy_a,
    avgInvestment
FROM monthsActive b
JOIN meProfitData a ON a.account_number = b.account_number;
GO