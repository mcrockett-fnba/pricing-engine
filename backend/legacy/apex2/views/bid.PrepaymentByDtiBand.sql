SET QUOTED_IDENTIFIER, ANSI_NULLS ON
GO
CREATE VIEW [bid].[PrepaymentByDtiBand] AS
SELECT 
    loanprepayment.dimension,
    loanprepayment.itinStatus,
    loanprepayment.band,
    CASE
        WHEN loanprepayment.band = 'Not calculated' THEN NULL
        WHEN loanprepayment.band = '0 - 0.35' THEN 0.00
        WHEN loanprepayment.band = '>0.35 - 0.43' THEN 0.36
        WHEN loanprepayment.band = '>0.43 - 0.50' THEN 0.44
        WHEN loanprepayment.band = '>0.50 - 0.55' THEN 0.51
        WHEN loanprepayment.band = '>0.55 - 0.60' THEN 0.56
        ELSE 0.61
    END AS lowerLimit,
	CASE
        WHEN loanprepayment.band = 'Not calculated' THEN NULL
        WHEN loanprepayment.band = '0 - 0.35' THEN 0.35
        WHEN loanprepayment.band = '>0.35 - 0.43' THEN 0.43
        WHEN loanprepayment.band = '>0.43 - 0.50' THEN 0.50
        WHEN loanprepayment.band = '>0.50 - 0.55' THEN 0.55
        WHEN loanprepayment.band = '>0.55 - 0.60' THEN 0.60
        ELSE 1.00
    END AS upperLimit,
    loanprepayment.prepaymentRate1Month,
    loanprepayment.prepaymentRate3Month,
    loanprepayment.prepaymentRate12Month,
	loanprepayment.prepaymentRateOverAll
FROM 
    bid.LoanPrePaymentRate loanprepayment
WHERE 
    loanprepayment.dimension = 'dtiBand';

GO