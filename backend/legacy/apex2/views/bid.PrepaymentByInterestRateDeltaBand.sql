SET QUOTED_IDENTIFIER, ANSI_NULLS ON
GO
CREATE VIEW [bid].[PrepaymentByInterestRateDeltaBand] AS

WITH _summedServicingcostsinLoanprepayment AS (
	SELECT dimension,band,itinStatus,SUM(totalOperatingCosts+costOfDefault) AS servicingCosts
	FROM bid.LoanPrePaymentRate
	GROUP BY dimension,
			 band,
			 itinStatus
)
SELECT 
    snap.dimension,
    snap.itinStatus,
    snap.band,
    CASE
        WHEN snap.band = '<=-3%' THEN -100.0000
        WHEN snap.band = '-2 to -2.99%' THEN -2.9999
        WHEN snap.band = '-1 to -1.99%' THEN -1.9999
		WHEN snap.band = '-0.99 to 0.99%' THEN -0.9999
        WHEN snap.band = '1 to 1.99%' THEN 1.0000
        WHEN snap.band = '2 to 2.99%' THEN 2.0000
        ELSE 3.0000
    END AS lowerLimit,
	CASE
        WHEN snap.band = '<=-3%' THEN -3.0000
        WHEN snap.band = '-2 to -2.99%' THEN -2.0000
        WHEN snap.band = '-1 to -1.99%' THEN -1.0000
		WHEN snap.band = '-0.99 to 0.99%' THEN 0.9999
        WHEN snap.band = '1 to 1.99%' THEN 1.9999
        WHEN snap.band = '2 to 2.99%' THEN 2.9999
        ELSE 100.00
    END AS upperLimit,
    snap.prepaymentRate1Month,
    snap.prepaymentRate3Month,
    snap.prepaymentRate12Month,
	snap.prepaymentRateOverAll,
	b.servicingCosts
FROM 
    bid.LoanPrePaymentRate snap
JOIN _summedServicingcostsinLoanprepayment b
	ON b.band = snap.band
	AND b.dimension = snap.dimension
	AND b.itinStatus = snap.itinStatus
WHERE 
    snap.dimension = 'interestRateDeltaBand';
GO