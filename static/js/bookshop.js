(function($){

	$.Bookshop = {
		"init": function(book) {
			var	table = $('#book-'+book.isbn+'-prices'),
				rows = table.find('tbody>tr'),
				total = rows.length,
				loaded = 0,
				lowestPrice = null,
				lowestElem = null;

			var	completed = function() {
					$(lowestElem).addClass('lowest').find('th').append(' <span>lowest</span>');
					$('#price-loader-help').text("Click on a Bookstore to go to the book page");
				};

			var	updateLowest = function(price, row) {
					if (lowestPrice == null) {
						lowestPrice = price;
						lowestElem  = row;
					}
					else {
						if (price < lowestPrice) {
							lowestPrice = price;
							lowestElem  = row;
						}
					}
				};

			rows.each(function(){
				var	name = this.className,
					shopTR = $(this),
					priceTD = shopTR.find('td.price');

				shopTR.addClass('loading');
				priceTD.text('loading');
				book['shop'] = name;

				$.get('/price', book, function(js, status, xhr){
					var	prices = JSON.parse(js),
						price = 0;

					shopTR.removeClass('loading');
					priceTD.text('');

					if (prices.length == 0 || prices.error) {
						shopTR.addClass('none');
						priceTD.text('none');
					}
					else {
						shopTR.addClass('priced');
						if (prices.length == 1) {
							var obj = prices[0];
							price = obj.price.toFixed(2);
							priceTD.html('<a href="'+obj.url+'">'+price+'</a>');
							updateLowest(price, shopTR);
						}
						else if (prices.length > 1) {
							for (var i=prices.length-1,obj,pRow,date; i>=0; i--) {
								obj = prices[i];
								date = [obj.posted.day, obj.posted.month, obj.posted.year].join('/');
								price = obj.price.toFixed(2);
								pRow = $('<tr class="'+name+' priced sub"><th scope="row" class="store">'+date+'</th><td class="price"><a href="'+obj.url+'">'+price+'</a></td></tr>');
								shopTR.after(pRow);
								updateLowest(price, pRow);
							}
						}
					}

					loaded = loaded + 1;
					if (loaded >= total) {
						completed();
					}
				}, 'application/json');
			});

			//rows.live('click', function(e){
			//	var row = $(this);
			//	if (!row.hasClass('loaded') || e.target.tagName.toUpperCase() == 'A') {
			//		return;
			//	}
			//	var url = row.find('a').attr('href');
			//	if (url) {
			//		window.location = url;
			//	}
			//});
		}
	};

})(jQuery);
