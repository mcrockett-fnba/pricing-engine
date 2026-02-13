SET QUOTED_IDENTIFIER, ANSI_NULLS ON
GO

CREATE    VIEW [bid].[PrepaymentByCollateralType] AS
SELECT * 
FROM bid.LoanPrePaymentRate
WHERE dimension='collateralType';
GO