SET QUOTED_IDENTIFIER, ANSI_NULLS ON
GO

CREATE   VIEW [bid].[PrepaymentByAbilityToRepayMethod] AS
SELECT * 
FROM bid.LoanPrePaymentRate
WHERE dimension='abilityToRepayMethodName';
GO