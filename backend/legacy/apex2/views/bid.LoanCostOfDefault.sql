SET QUOTED_IDENTIFIER, ANSI_NULLS ON
GO
CREATE      VIEW [bid].[LoanCostOfDefault] AS 
-- Getting the accounts separately
WITH meProfitData AS (
SELECT 
    a.account_number,
	SUM(CASE WHEN a.data_point_id = 135 THEN a.data_value ELSE 0 END) AS reo_overhead,
	SUM(CASE WHEN a.data_point_id = 150 THEN a.data_value ELSE 0 END) AS legal_fees,
	SUM(CASE WHEN a.data_point_id = 160 THEN a.data_value ELSE 0 END) AS property_taxes,
	SUM(CASE WHEN a.data_point_id = 170 THEN a.data_value ELSE 0 END) AS inventory,
	SUM(CASE WHEN a.data_point_id = 190 THEN a.data_value ELSE 0 END) AS hud,
	SUM(CASE WHEN a.data_point_id = 70 THEN a.data_value ELSE 0 END) AS resale,
	SUM(CASE WHEN a.data_point_id = 140 THEN a.data_value ELSE 0 END) AS write_down
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
    a.reo_overhead,
    a.reo_overhead / 48 * 12 AS reo_overhead_a,
    a.legal_fees,
    a.legal_fees / IIF(b.months_active < 12, 12, b.months_active) * 12 AS legal_fees_a,
    a.property_taxes,
    a.property_taxes /  48 * 12  AS property_taxes_a,
    a.inventory,
    a.inventory /  48 * 12 AS inventory_a,
    a.hud,
    a.hud /  48 * 12  AS hud_a,
	a.resale,
    a.resale /  48 * 12  AS resale_a,
	a.write_down,
    a.write_down /  48 * 12  AS write_down_a,
    avgInvestment
FROM monthsActive b
JOIN meProfitData a ON a.account_number = b.account_number;
GO