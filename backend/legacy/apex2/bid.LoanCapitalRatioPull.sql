SET QUOTED_IDENTIFIER, ANSI_NULLS ON
GO
CREATE PROCEDURE [bid].[LoanCapitalRatioPull] AS 
	DELETE FROM bid.LoanCapitalRatio


	INSERT INTO package.bid.LoanCapitalRatio
	(
		dateloaded,
	    itinstatus,
	    creditBand,
	    capitalRatio
	)
    SELECT
		GETDATE(),
        loanprepayment.itinStatus,
        loanprepayment.creditBand,
        SUM(capital.capital)/SUM(capital.averageInvestment) AS capitalRatio
    FROM package.bid.LoanPrePaymentRateDetail AS loanprepayment
    JOIN relmeom.profit.investmentAndCapital AS capital
        ON capital.accountNumber = loanprepayment.account_number
       AND capital.period = loanprepayment.period
    WHERE capital.averageInvestment > 0
    GROUP BY
        loanprepayment.itinStatus,
        loanprepayment.creditBand;

GO