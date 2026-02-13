SET QUOTED_IDENTIFIER, ANSI_NULLS ON
GO
CREATE    VIEW [bid].[PrepaymentByCreditBand] AS

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
		WHEN loanprepayment.band = 'No Score' THEN 555
        WHEN loanprepayment.band = '< 576' THEN 0
        WHEN loanprepayment.band = '576-600' THEN 576
        WHEN loanprepayment.band = '601-625' THEN 601
        WHEN loanprepayment.band = '626-650' THEN 626
        WHEN loanprepayment.band = '651-675' THEN 651
        WHEN loanprepayment.band = '676-700' THEN 676
        WHEN loanprepayment.band = '701-725' THEN 701
        WHEN loanprepayment.band = '726-750' THEN 726
        ELSE 751
    END AS lowerLimit,
	CASE 
		WHEN loanprepayment.band = 'No Score' THEN 555
        WHEN loanprepayment.band = '< 576' THEN 575
        WHEN loanprepayment.band = '576-600' THEN 600
        WHEN loanprepayment.band = '601-625' THEN 625
        WHEN loanprepayment.band = '626-650' THEN 650
        WHEN loanprepayment.band = '651-675' THEN 675
        WHEN loanprepayment.band = '676-700' THEN 700
        WHEN loanprepayment.band = '701-725' THEN 725
        WHEN loanprepayment.band = '726-750' THEN 750
        ELSE 1000
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
    loanprepayment.dimension = 'creditBand';

GO