SET QUOTED_IDENTIFIER, ANSI_NULLS ON
GO
CREATE PROCEDURE [bid].[activePipelineFetch]
	@sortBy VARCHAR(100) = NULL,
	@pageShowing INT = NULL,
	@searchText VARCHAR(100) = NULL,
	@sortDirection VARCHAR(100) = NULL
AS
BEGIN;

	DECLARE @statement NVARCHAR(MAX);
	
	SELECT @searchText = COALESCE(@searchText, '');

	CREATE TABLE #bids(bidId INT, name VARCHAR(100), createdBy VARCHAR(100), createdOn DATETIME2, currentBalance NUMERIC(12, 2),
					   bidStatus VARCHAR(100), loanCount INT, sellerId INT, sellerName VARCHAR(100), commitmentNumber VARCHAR(100), keepIt INT);

	INSERT #bids(bidId, name, createdBy, createdOn, currentBalance, bidStatus, loanCount, sellerId, sellerName, commitmentNumber)
	SELECT bidId, name, createdBy, createdOn, currentBalance, bidStatus, loanCount, sellerId, sellerName, commitmentNumber
	FROM bid.bidState bidState
	WHERE bidStatusId NOT IN(4, 7, 8, 9, 12)
	AND isActiveBid = 1

	IF(@searchText <> '')
	BEGIN;
		UPDATE bids
		SET keepIt = 1
		FROM #bids bids
		WHERE name LIKE(@searchText + '%')
		OR commitmentNumber = TRY_CAST(@searchText AS INT)
		OR sellerName LIKE(@searchText + '%')
		OR EXISTS(SELECT * 
				  FROM bid.loan x 
				  WHERE x.bidId = bids.bidId 
				  AND (x.sellerLoanNumber LIKE(@searchText + '%') 
					   OR 					
					   x.brokerName LIKE (@searchText + '%')
					   OR
					   x.propertyAddress LIKE (@searchText + '%')
					  )
				 );
	END;

	SELECT @searchText = utilities.sanitizeDynamicSql(@searchText)
	SELECT @sortBy = utilities.sanitizeDynamicSql(@sortBy);
	SELECT @sortDirection = utilities.sanitizeDynamicOrderByDirection(@sortDirection);

	IF(COALESCE(@sortBy, '') = '')
	BEGIN;
		SELECT @sortBy = 'createdOn';
	END;

	SELECT @statement = 
		'WITH _sort AS
		 (
			SELECT bidId,
				   ROW_NUMBER() OVER(ORDER BY CASE WHEN ' + @sortBy + ' IS NOT NULL THEN 1 ELSE 2 END, ' + @sortBy + ' ' + @sortDirection + ', createdOn DESC) AS rowNumber
			 FROM #bids
			 WHERE ''' + @searchText + ''' = '''' OR keepIt = 1
		 ) 
		 SELECT bids.bidId,
				bids.name,
				bids.createdBy,
				FORMAT(bids.createdOn, ''MM/dd/yyyy'') AS createdOn,
				FORMAT(bids.createdOn, ''MM/dd/yyyy h:mm tt'') AS entryDate,
				bids.currentBalance,
				bids.bidStatus,
				bids.loanCount,
				_sort.rowNumber,
				COUNT(*) OVER() AS bidCount,
				DATEDIFF(DAY, MIN(createdOn) OVER(), SYSDATETIME()) AS oldestBidDays,
				sellerId,
				sellerName,
				CAST(commitmentNumber AS INT) AS commitmentNumber
		 FROM #bids bids
		 JOIN _sort 
			ON _sort.bidId = bids.bidId';

	EXECUTE utilities.executeSql @statement = @statement,
								 @pageShowing = @pageShowing;

END;

GO