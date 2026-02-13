SET QUOTED_IDENTIFIER, ANSI_NULLS ON
GO
CREATE   VIEW [bid].[PrepaymentByLoanSizeBand] AS

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
        WHEN loanprepayment.band = '$0 - $49,999' THEN 0
        WHEN loanprepayment.band = '$50,000 - $99,999' THEN 50000
        WHEN loanprepayment.band = '$100,000 - $149,999' THEN 100000
        WHEN loanprepayment.band = '$150,000 - $199,999' THEN 150000
        WHEN loanprepayment.band = '$200,000 - $249,999' THEN 200000
        WHEN loanprepayment.band = '$250,000 - $499,999' THEN 250000
        WHEN loanprepayment.band = '$500,000 - $999,999' THEN 500000
        ELSE 1000000
    END AS lowerLimit,
    CASE
        WHEN loanprepayment.band = '$0 - $49,999' THEN 49999
        WHEN loanprepayment.band = '$50,000 - $99,999' THEN 99999
        WHEN loanprepayment.band = '$100,000 - $149,999' THEN 149999
        WHEN loanprepayment.band = '$150,000 - $199,999' THEN 199999
        WHEN loanprepayment.band = '$200,000 - $249,999' THEN 249999
        WHEN loanprepayment.band = '$250,000 - $499,999' THEN 499999
        WHEN loanprepayment.band = '$500,000 - $999,999' THEN 999999
        ELSE 10000000
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
    loanprepayment.dimension = 'loanSizeBand';

GO