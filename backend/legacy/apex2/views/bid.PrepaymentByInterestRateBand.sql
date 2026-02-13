SET QUOTED_IDENTIFIER, ANSI_NULLS ON
GO
CREATE     VIEW [bid].[PrepaymentByInterestRateBand] AS

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
        WHEN loanprepayment.band = '<2.0' THEN 0.00000000
        WHEN loanprepayment.band = '2.0-2.99' THEN 2.00000000
        WHEN loanprepayment.band = '3.0-3.99' THEN 3.00000000
        WHEN loanprepayment.band = '4.0-4.99' THEN 4.00000000
        WHEN loanprepayment.band = '5.0-5.99' THEN 5.00000000
        WHEN loanprepayment.band = '6.0-6.99' THEN 6.00000000
        WHEN loanprepayment.band = '7.0-7.99' THEN 7.00000000
        WHEN loanprepayment.band = '8.0-8.99' THEN 8.00000000
        WHEN loanprepayment.band = '9.0-9.99' THEN 9.00000000
        ELSE 10.00000000
    END AS lowerLimit,
	CASE 
        WHEN loanprepayment.band = '<2.0' THEN 1.99999999
        WHEN loanprepayment.band = '2.0-2.99' THEN 2.99999999
        WHEN loanprepayment.band = '3.0-3.99' THEN 3.99999999
        WHEN loanprepayment.band = '4.0-4.99' THEN 4.99999999
        WHEN loanprepayment.band = '5.0-5.99' THEN 5.99999999
        WHEN loanprepayment.band = '6.0-6.99' THEN 6.99999999
        WHEN loanprepayment.band = '7.0-7.99' THEN 7.99999999
        WHEN loanprepayment.band = '8.0-8.99' THEN 8.99999999
        WHEN loanprepayment.band = '9.0-9.99' THEN 9.99999999
        ELSE 100.00000000
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
    loanprepayment.dimension = 'interestRateBand';

GO