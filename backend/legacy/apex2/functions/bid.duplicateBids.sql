SET QUOTED_IDENTIFIER, ANSI_NULLS ON
GO

CREATE   FUNCTION [bid].[duplicateBids](@sellerLoanNumber VARCHAR(100), @propertyAddress VARCHAR(100), @daysToSearch INT)
RETURNS TABLE
AS

RETURN 

WITH _businessDays AS
(
	SELECT date, 
		   ROW_NUMBER() OVER(ORDER BY date DESC) AS daysInThePast
	FROM sybsystemprocs.fnba.spt_workdays
	WHERE date < CAST(SYSDATETIME() AS DATE)
	ORDER BY date DESC
	OFFSET 0 ROWS FETCH NEXT COALESCE(@daysToSearch, 30) ROWS ONLY
),
_dataset AS
(
	SELECT bidState.bidId,
		   bidState.name,
		   bidState.createdOn,
		   bidState.createdById
	FROM bid.bidState bidState
	JOIN bid.loan loan
		ON loan.bidId = bidState.bidId
	JOIN _businessDays
		ON _businessDays.daysInThePast = COALESCE(@daysToSearch, 30)
	WHERE bidState.createdOn >= _businessDays.date
	AND (COALESCE(@sellerLoanNumber, '') = '' OR loan.sellerLoanNumber = @sellerLoanNumber)
	AND (COALESCE(@propertyAddress, '') = '' OR loan.propertyAddress LIKE(@propertyAddress + '%'))
	GROUP BY bidState.bidId, 
			 bidState.name, 
			 bidState.createdOn, 
			 bidState.createdById
)
SELECT _dataset.bidId,
	   _dataset.name AS bidName,
	   FORMAT(_dataset.createdOn, 'MM/dd/yyyy hh:mm:ss') AS createdOn,
	   associate.first_name + ' ' + associate.last_name as loanOfficer
FROM _dataset
JOIN perdb.fnba.associate associate
	ON associate.assoc_id = _dataset.createdById
GO