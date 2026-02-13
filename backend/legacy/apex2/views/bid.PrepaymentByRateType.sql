SET QUOTED_IDENTIFIER, ANSI_NULLS ON
GO
CREATE      VIEW [bid].[PrepaymentByRateType] AS

WITH _summedServicingcostsinLoanprepayment AS (
	SELECT dimension,band,itinStatus,SUM(totalOperatingCosts+costOfDefault) AS servicingCosts
	FROM bid.LoanPrePaymentRate
	GROUP BY dimension,
			 band,
			 itinStatus
)
SELECT a.*,b.servicingCosts
FROM bid.LoanPrePaymentRate a
JOIN _summedServicingcostsinLoanprepayment b 
ON b.band = a.band
AND b.dimension = a.dimension
AND b.itinStatus = a.itinStatus
WHERE a.dimension='rateType'
GO