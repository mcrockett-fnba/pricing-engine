SET QUOTED_IDENTIFIER, ANSI_NULLS ON
GO
CREATE    VIEW [bid].[PrepaymentByLtvBand] AS

WITH _summedServicingcostsinLoanprepayment AS (
	SELECT dimension,band,itinStatus,SUM(totalOperatingCosts+costOfDefault) AS servicingCosts
	FROM bid.LoanPrePaymentRate
	GROUP BY dimension,
			 band,
			 itinStatus
)
SELECT 
    loanprepayment.dimension,
    loanprepayment.itinStatus,
    loanprepayment.band,
    CASE
        WHEN loanprepayment.band = '< 75%' THEN 0.0000
        WHEN loanprepayment.band = '75% - 79.99%' THEN 75.0000
        WHEN loanprepayment.band = '80% - 84.99%' THEN 80.0000
        WHEN loanprepayment.band = '85% - 89.99%' THEN 85.0000
        ELSE 90.0000
    END AS lowerLimit,
    CASE
        WHEN loanprepayment.band = '< 75%' THEN 74.9999
        WHEN loanprepayment.band = '75% - 79.99%' THEN 79.9999
        WHEN loanprepayment.band = '80% - 84.99%' THEN 84.9999
        WHEN loanprepayment.band = '85% - 89.99%' THEN 89.9999
        ELSE 1000.0000
    END AS upperLimit,
    loanprepayment.prepaymentRate1Month,
    loanprepayment.prepaymentRate3Month,
    loanprepayment.prepaymentRate12Month,
	loanprepayment.prepaymentRateOverAll,
	b.servicingCosts
FROM 
    bid.LoanPrePaymentRate loanprepayment
JOIN _summedServicingcostsinLoanprepayment b
	ON b.band = loanprepayment.band
	AND b.dimension = loanprepayment.dimension
	AND b.itinStatus = loanprepayment.itinStatus
WHERE 
    loanprepayment.dimension = 'ltvBand';

GO