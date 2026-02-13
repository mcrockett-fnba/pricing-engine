SET QUOTED_IDENTIFIER, ANSI_NULLS ON
GO
CREATE PROCEDURE [bid].[LoanPrePaymentRatePush]
AS
BEGIN
    DELETE FROM package.bid.LoanPrePaymentRate;

	DECLARE @timeStamp DATETIME = GETDATE();
	SELECT * INTO #allloansdata FROM package.bid.LoanPrePaymentRateDetail;
	SELECT * INTO #totaloperatingcosts FROM package.bid.LoanTotalOperatingCosts;
	SELECT * INTO #LoanCostOfDefault FROM package.bid.LoanCostOfDefault;
	;WITH _rankperiods AS (SELECT *,ROW_NUMBER() OVER (PARTITION BY account_number ORDER BY period DESC) AS rn FROM #allloansdata)
	SELECT * INTO #loans_prev FROM _rankperiods WHERE rn=1;
	INSERT INTO package.bid.LoanPrePaymentRate
	(
		dateloaded,
		dimension,
		itinStatus,
		band,
		prepaymentRate1Month,
		prepaymentRate3Month,
		prepaymentRate12Month,
		prepaymentRateOverAll,
		totalOperatingCosts,
		probabiltyOfDefault,
		costOfDefault,
		collateralGainOrLoss
	)
	SELECT 
		@timeStamp AS dateloaded,
		dimension,
		itinStatus,
		CAST(band AS VARCHAR(255)) AS band,
		SUM(IIF(rolling1 = 1, actualPaymentAmount, 0.00)) / 
			ISNULL(SUM(NULLIF(IIF(rolling1 = 1, expectedPaymentAmount, 0.00), 0.00)), 1.00) AS prepaymentRate1Month,
		SUM(IIF(rolling3 = 1, actualPaymentAmount, 0.00)) / 
			ISNULL(SUM(NULLIF(IIF(rolling3 = 1, expectedPaymentAmount, 0.00), 0.00)), 1.00) AS prepaymentRate3Month,
		SUM(IIF(rolling12 = 1, actualPaymentAmount, 0.00)) / 
			ISNULL(SUM(NULLIF(IIF(rolling12 = 1, expectedPaymentAmount, 0.00), 0.00)), 1.00) AS prepaymentRate12Month,
		SUM(IIF(rollingAll = 1, actualPaymentAmount, 0.00)) / 
			ISNULL(SUM(NULLIF(IIF(rollingAll = 1, expectedPaymentAmount, 0.00), 0.00)), 1.00) AS prepaymentRateOverAll,
		NULL AS totalOperatingCosts,
		NULL AS probabiltyOfDefault,
		NULL AS costOfDefault,
		NULL AS collateralGainOrLoss
	FROM #allloansdata
	CROSS APPLY (
		VALUES
		('creditBand', CAST(creditBand AS VARCHAR(255))),
		('interestRateBand', CAST(interestRateBand AS VARCHAR(255))),
		('dtiBand', CAST(dtiBand AS VARCHAR(255))),
		('ltvBand', CAST(ltvBand AS VARCHAR(255))),
		('loanSizeBand', CAST(loanSizeBand AS VARCHAR(255))),
		('interestRateDeltaBand', CAST(interestRateDeltaBand AS VARCHAR(255))),
		('abilityToRepayMethodName', CAST(abilityToRepayMethodName AS VARCHAR(255))),
		('collateralState', CAST(collateralState AS VARCHAR(255))),
		('collateralType', CAST(collateralType AS VARCHAR(255))),
		('lienPosition', CAST(lienPosition AS VARCHAR(255))),
		('rateType', CAST(rateType AS VARCHAR(255)))
	) AS Dim(dimension, band)
	GROUP BY itinStatus, dimension, band
	ORDER BY Dim.dimension,itinStatus,Dim.band;

	;WITH costs AS(
	SELECT
		@timeStamp AS dateloaded,
		dimension,
		itinStatus,
		CAST(band AS VARCHAR(255)) AS band,
		(SUM(profit.non_inventory_a) + SUM(profit.customer_service_a) + 
			 SUM(profit.coll_fore_a) + SUM(profit.bankruptcy_a)) / 
			 IIF(SUM(profit.avgInvestment) = 0, 1, SUM(profit.avgInvestment)) AS totalOperatingCosts,
		(SUM(CostOfDefault.reo_overhead_a+CostOfDefault.legal_fees_a+CostOfDefault.property_taxes_a+CostOfDefault.inventory_a
			+CostOfDefault.hud_a)/
			IIF(SUM(profit.avgInvestment) = 0, 1, SUM(profit.avgInvestment))) AS costOfDefault,
		(SUM(CostOfDefault.write_down_a-CostOfDefault.resale_a)/
			IIF(SUM(profit.avgInvestment) = 0, 1, SUM(profit.avgInvestment))) AS collateralGainOrLoss,
		(CAST(SUM(isCostOfDefault) AS DECIMAL (15,4))/CAST(COUNT(*) AS DECIMAL(15,4))) AS probabiltyOfDefault
	FROM #loans_prev loans
	LEFT JOIN #totaloperatingcosts profit ON profit.account_number = loans.account_number
	LEFT JOIN #LoanCostOfDefault CostOfDefault ON CostOfDefault.account_number = loans.account_number
	CROSS APPLY (
		VALUES
			('creditBand', CAST(creditBand AS VARCHAR(255))),
			('interestRateBand', CAST(interestRateBand AS VARCHAR(255))),
			('dtiBand', CAST(dtiBand AS VARCHAR(255))),
			('ltvBand', CAST(ltvBand AS VARCHAR(255))),
			('loanSizeBand', CAST(loanSizeBand AS VARCHAR(255))),
			('interestRateDeltaBand', CAST(interestRateDeltaBand AS VARCHAR(255))),
			('abilityToRepayMethodName', CAST(abilityToRepayMethodName AS VARCHAR(255))),
			('collateralState', CAST(collateralState AS VARCHAR(255))),
			('collateralType', CAST(collateralType AS VARCHAR(255))),
			('lienPosition', CAST(lienPosition AS VARCHAR(255))),
			('rateType', CAST(rateType AS VARCHAR(255)))
	) AS Dim(dimension, band)
	GROUP BY itinStatus,dimension, band
	)
	UPDATE r
	SET r.totalOperatingCosts = c.totalOperatingCosts, 
	r.costOfDefault=c.costOfDefault,
	r.collateralGainOrLoss=c.collateralGainOrLoss,
	r.probabiltyOfDefault=c.probabiltyOfDefault
	FROM package.bid.LoanPrePaymentRate AS r
	JOIN costs AS c
		ON r.dimension = c.dimension
		AND r.band = c.band
		AND r.itinStatus = c.itinStatus
END;
--runci
GO