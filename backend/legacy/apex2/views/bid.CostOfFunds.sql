SET QUOTED_IDENTIFIER, ANSI_NULLS ON
GO
CREATE   VIEW [bid].[CostOfFunds]
AS

SELECT 
	packages.pkg_purchase_id
	, savedCostOfFunds = ISNULL(packages.costOfFunds, 0.00)
	, currentCostOfFunds = CAST(costOfFunds.costOfFunds/CAST(100.0 AS decimal(5, 1)) AS decimal(12, 7))
FROM fnba.pkg_purchase packages
CROSS JOIN acqdb.fnba.cofByDivision costOfFunds 
WHERE costOfFunds.division = 'PPD BULK';
GO